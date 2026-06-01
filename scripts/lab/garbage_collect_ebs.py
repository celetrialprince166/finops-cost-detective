#!/usr/bin/env python3
"""Cost Detective lab — standalone EBS garbage collector.

Lists and (optionally) deletes unattached EBS volumes in the target region.

Design goals:
  * Dry-run by default. ``--delete`` is required for any destructive action.
  * Tag filtering via ``--tag CostCenter=Lab`` (repeatable). All supplied
    tags must match (AND), preventing accidental cleanup of unrelated volumes.
  * Grace period via ``--grace-days N``. Volumes younger than ``N`` days are
    skipped. Default 7 — matches the in-pipeline CloudSweep scanner.
  * Optional safety snapshot via ``--snapshot-first`` before each delete.
  * Itemised cost estimate using the same rate table as
    ``src.python.scanners.ebs``.

Exit codes:
  0 = success (dry-run or all deletions succeeded)
  1 = at least one volume failed to delete or snapshot
  2 = invalid arguments / refused due to safety guard

Examples:
  # Dry-run (default) — list lab zombies
  python scripts/lab/garbage_collect_ebs.py --region eu-west-1 --tag CostCenter=Lab

  # Real delete with safety snapshot
  python scripts/lab/garbage_collect_ebs.py --region eu-west-1 \
      --tag CostCenter=Lab --grace-days 0 --delete --snapshot-first
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

import boto3

# Same rates as src/python/scanners/ebs.py — keep in sync.
VOLUME_TYPE_RATES: dict[str, float] = {
    "gp3": 0.08,
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.025,
}


@dataclass(frozen=True)
class GcOptions:
    region: str
    tag_filters: list[tuple[str, str]]
    grace_days: int
    delete: bool
    snapshot_first: bool


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> GcOptions:
    parser = argparse.ArgumentParser(
        description="Cost Detective EBS garbage collector (dry-run by default)."
    )
    parser.add_argument(
        "--region",
        default="eu-west-1",
        help="AWS region to scan (default: eu-west-1).",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Tag filter; repeatable. All supplied tags must match. "
        "Example: --tag CostCenter=Lab --tag Project=cost-detective.",
    )
    parser.add_argument(
        "--grace-days",
        type=int,
        default=7,
        help="Skip volumes younger than this many days (default: 7).",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete matching volumes. Without this, the script "
        "only lists candidates (dry-run).",
    )
    parser.add_argument(
        "--snapshot-first",
        action="store_true",
        help="When deleting, take a safety snapshot before each delete.",
    )
    ns = parser.parse_args(argv)

    tag_filters: list[tuple[str, str]] = []
    for raw in ns.tag:
        if "=" not in raw:
            parser.error(f"Invalid --tag value {raw!r}; expected KEY=VALUE.")
        key, _, value = raw.partition("=")
        tag_filters.append((key, value))

    return GcOptions(
        region=ns.region,
        tag_filters=tag_filters,
        grace_days=ns.grace_days,
        delete=ns.delete,
        snapshot_first=ns.snapshot_first,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def estimate_monthly_cost_usd(volume: dict) -> float:
    size_gb = float(volume["Size"])
    vol_type = volume.get("VolumeType", "gp3")
    rate = VOLUME_TYPE_RATES.get(vol_type, 0.10)
    return round(size_gb * rate, 2)


def find_candidates(
    ec2_client,
    tag_filters: Iterable[tuple[str, str]],
    grace_days: int,
    now: datetime | None = None,
) -> list[dict]:
    """Return unattached volumes matching tag_filters and older than grace_days."""
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=grace_days)

    filters = [{"Name": "status", "Values": ["available"]}]
    for key, value in tag_filters:
        filters.append({"Name": f"tag:{key}", "Values": [value]})

    response = ec2_client.describe_volumes(Filters=filters)
    volumes = response.get("Volumes", [])
    return [v for v in volumes if v["CreateTime"] <= cutoff]


def snapshot_volume(ec2_client, volume: dict) -> str:
    """Create a safety snapshot. Returns SnapshotId."""
    tags = list(volume.get("Tags", [])) + [
        {"Key": "PreDeleteSnapshot", "Value": "true"},
        {"Key": "SourceVolumeId", "Value": volume["VolumeId"]},
    ]
    response = ec2_client.create_snapshot(
        VolumeId=volume["VolumeId"],
        Description=f"Pre-GC safety snapshot of {volume['VolumeId']}",
        TagSpecifications=[
            {"ResourceType": "snapshot", "Tags": tags},
        ],
    )
    return response["SnapshotId"]


def delete_volume(ec2_client, volume_id: str) -> None:
    ec2_client.delete_volume(VolumeId=volume_id)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_volume_line(volume: dict) -> str:
    cost = estimate_monthly_cost_usd(volume)
    tag_str = ",".join(
        f"{t['Key']}={t['Value']}" for t in volume.get("Tags", []) if t.get("Key")
    )
    return (
        f"  {volume['VolumeId']:<22} "
        f"{volume.get('VolumeType', '?'):<5} "
        f"{volume['Size']:>4}GiB "
        f"${cost:>6.2f}/mo "
        f"created={volume['CreateTime'].strftime('%Y-%m-%d')} "
        f"tags=[{tag_str}]"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(opts: GcOptions, ec2_client=None, *, stdout=sys.stdout) -> int:
    if opts.delete and not opts.tag_filters:
        print(
            "ERROR: --delete requires at least one --tag filter to prevent "
            "account-wide deletion. Aborting.",
            file=stdout,
        )
        return 2

    ec2 = ec2_client or boto3.client("ec2", region_name=opts.region)

    candidates = find_candidates(ec2, opts.tag_filters, opts.grace_days)

    print(
        f"Region={opts.region}  Filters="
        f"{opts.tag_filters or '(none)'}  GraceDays={opts.grace_days}  "
        f"Mode={'DELETE' if opts.delete else 'DRY-RUN'}",
        file=stdout,
    )

    if not candidates:
        print("No matching unattached volumes found.", file=stdout)
        return 0

    total_cost = 0.0
    print(f"Found {len(candidates)} candidate(s):", file=stdout)
    for vol in candidates:
        print(format_volume_line(vol), file=stdout)
        total_cost += estimate_monthly_cost_usd(vol)
    print(f"Estimated monthly waste: ${total_cost:.2f}", file=stdout)

    if not opts.delete:
        print(
            f"Dry-run only. Would delete {len(candidates)} volume(s). "
            "Re-run with --delete to act.",
            file=stdout,
        )
        return 0

    failures = 0
    for vol in candidates:
        vol_id = vol["VolumeId"]
        try:
            if opts.snapshot_first:
                snap_id = snapshot_volume(ec2, vol)
                print(f"  snapshot {vol_id} -> {snap_id}", file=stdout)
            delete_volume(ec2, vol_id)
            print(f"  deleted  {vol_id}", file=stdout)
        except Exception as exc:  # pragma: no cover - logged for visibility
            failures += 1
            print(f"  FAILED   {vol_id}: {exc}", file=stdout)

    if failures:
        print(f"Done with {failures} failure(s).", file=stdout)
        return 1

    print(f"Done. Deleted {len(candidates)} volume(s).", file=stdout)
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
