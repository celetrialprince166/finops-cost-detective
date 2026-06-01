"""Remediator - performs cleanup actions on idle resources."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

import boto3

from .config import settings
from .models import Finding
from .state import StateStore, today_iso


@dataclass
class RemediationResult:
    finding: Finding
    action: str
    status: str
    snapshot_id: str | None
    correlation_id: str


def remediate(
    finding: Finding, dry_run: bool = False, state_store: StateStore | None = None
) -> RemediationResult:
    store = state_store or StateStore()
    correlation_id = str(uuid.uuid4())

    existing = store.get_item(finding.resource_id, today_iso())
    # Only skip if a remediation record already exists (has an "action" key).
    # A record with status == "found" was written by the scanner and should not
    # prevent the remediator from running.
    if existing and existing.get("action"):
        return RemediationResult(
            finding=finding,
            action="skipped",
            status="already_processed",
            snapshot_id=None,
            correlation_id=correlation_id,
        )

    if finding.resource_type == "ebs":
        result = _remediate_ebs(finding, dry_run)
    elif finding.resource_type == "rds":
        result = _remediate_rds(finding, dry_run)
    elif finding.resource_type == "eip":
        result = _remediate_eip(finding, dry_run)
    elif finding.resource_type == "snapshot":
        result = _remediate_snapshot(finding, dry_run)
    else:
        result = RemediationResult(
            finding=finding,
            action="unknown",
            status="skipped",
            snapshot_id=None,
            correlation_id=correlation_id,
        )

    store.put_item(
        {
            "resource_id": finding.resource_id,
            "scan_date": today_iso(),
            "action": result.action,
            "status": result.status,
            "correlation_id": correlation_id,
            "snapshot_id": result.snapshot_id,
        }
    )

    return result


def _remediate_ebs(finding: Finding, dry_run: bool) -> RemediationResult:
    ec2 = boto3.client("ec2", region_name=finding.region)
    snapshot_id = None

    if not dry_run:
        snapshot_id = _create_snapshot(ec2, finding.resource_id, finding.region)
        ec2.delete_volume(VolumeId=finding.resource_id)

    action = "deleted" if snapshot_id else "skipped"
    status = "dry_run" if dry_run else "success"
    return RemediationResult(
        finding=finding,
        action=action,
        status=status,
        snapshot_id=snapshot_id,
        correlation_id=str(uuid.uuid4()),
    )


def _remediate_rds(finding: Finding, dry_run: bool) -> RemediationResult:
    rds = boto3.client("rds", region_name=finding.region)
    snapshot_id = None

    if not dry_run:
        snapshot_id = f"cloudsweep-{finding.resource_id}-{today_iso()}"
        try:
            rds.create_db_snapshot(
                DBSnapshotIdentifier=snapshot_id,
                DBInstanceIdentifier=finding.resource_id,
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "RDS safety snapshot failed for %s: %s", finding.resource_id, exc
            )
            snapshot_id = None

        rds.stop_db_instance(DBInstanceIdentifier=finding.resource_id)

    status = "dry_run" if dry_run else "success"
    return RemediationResult(
        finding=finding,
        action="stopped",
        status=status,
        snapshot_id=snapshot_id,
        correlation_id=str(uuid.uuid4()),
    )


def _remediate_eip(finding: Finding, dry_run: bool) -> RemediationResult:
    ec2 = boto3.client("ec2", region_name=finding.region)

    if not dry_run:
        ec2.release_address(AllocationId=finding.resource_id)

    status = "dry_run" if dry_run else "success"
    return RemediationResult(
        finding=finding,
        action="released",
        status=status,
        snapshot_id=None,
        correlation_id=str(uuid.uuid4()),
    )


def _remediate_snapshot(finding: Finding, dry_run: bool) -> RemediationResult:
    ec2 = boto3.client("ec2", region_name=finding.region)

    if not dry_run:
        ec2.delete_snapshot(SnapshotId=finding.resource_id)

    status = "dry_run" if dry_run else "success"
    return RemediationResult(
        finding=finding,
        action="deleted",
        status=status,
        snapshot_id=None,
        correlation_id=str(uuid.uuid4()),
    )


def handler(event: dict, context) -> dict:
    """Remediate Lambda entry point — executes cleanup on classified findings.

    Receives evaluate Lambda output (findings list + decision), calls remediate()
    per finding respecting dry_run from settings, and returns a results summary
    consumed by the notify Lambda.
    """
    findings_dicts: list[dict] = event.get("findings", [])
    dry_run: bool = settings.dry_run

    results = []
    for f_dict in findings_dicts:
        try:
            finding = Finding(**f_dict)
            result = remediate(finding, dry_run=dry_run)
            result_dict = asdict(result)
            result_dict["resource_id"] = finding.resource_id
            result_dict["resource_type"] = finding.resource_type
            results.append(result_dict)
        except Exception as exc:
            results.append(
                {
                    "resource_id": f_dict.get("resource_id", "unknown"),
                    "status": "error",
                    "error": str(exc),
                }
            )

    return {
        "count": len(results),
        "results": results,
        "dry_run": dry_run,
    }


def _create_snapshot(ec2, volume_id: str, region: str) -> str | None:
    try:
        response = ec2.create_snapshot(
            VolumeId=volume_id,
            Description=f"Backup before delete by CloudSweep",
        )
        return response["SnapshotId"]
    except Exception:
        return None
