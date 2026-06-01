"""Unit tests for scripts/lab/garbage_collect_ebs.py."""

from __future__ import annotations

import io
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Import the script directly (scripts/lab/ is not a package).
# ---------------------------------------------------------------------------

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "lab"
    / "garbage_collect_ebs.py"
)
_MODULE_NAME = "garbage_collect_ebs"


def _load_script_module():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec so @dataclass can resolve cls.__module__
    # on Python 3.14+ (where dataclasses internals consult sys.modules).
    sys.modules[_MODULE_NAME] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gc = _load_script_module()
GcOptions = gc.GcOptions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _vol(
    vol_id: str = "vol-aaa",
    size: int = 8,
    vol_type: str = "gp3",
    age_days: int = 10,
    tags: list[tuple[str, str]] | None = None,
) -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=age_days)
    return {
        "VolumeId": vol_id,
        "Size": size,
        "VolumeType": vol_type,
        "State": "available",
        "CreateTime": created,
        "Tags": [{"Key": k, "Value": v} for k, v in (tags or [])],
    }


@pytest.fixture
def ec2():
    return MagicMock()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults(self):
        opts = gc.parse_args([])
        assert opts.region == "eu-west-1"
        assert opts.tag_filters == []
        assert opts.grace_days == 7
        assert opts.delete is False
        assert opts.snapshot_first is False

    def test_tag_filter_repeatable(self):
        opts = gc.parse_args(
            ["--tag", "CostCenter=Lab", "--tag", "Project=cost-detective"]
        )
        assert opts.tag_filters == [
            ("CostCenter", "Lab"),
            ("Project", "cost-detective"),
        ]

    def test_invalid_tag_format_exits(self):
        with pytest.raises(SystemExit):
            gc.parse_args(["--tag", "no_equals_here"])

    def test_delete_and_snapshot_flags(self):
        opts = gc.parse_args(
            ["--region", "us-east-1", "--delete", "--snapshot-first"]
        )
        assert opts.region == "us-east-1"
        assert opts.delete is True
        assert opts.snapshot_first is True

    def test_grace_days(self):
        opts = gc.parse_args(["--grace-days", "0"])
        assert opts.grace_days == 0


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


class TestCostEstimate:
    @pytest.mark.parametrize(
        "vol_type,size,expected",
        [
            ("gp3", 100, 8.0),
            ("gp2", 100, 10.0),
            ("io1", 50, 6.25),
            ("st1", 200, 9.0),
            ("unknown", 100, 10.0),  # falls back to 0.10
        ],
    )
    def test_rates(self, vol_type, size, expected):
        v = _vol(size=size, vol_type=vol_type)
        assert gc.estimate_monthly_cost_usd(v) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# find_candidates
# ---------------------------------------------------------------------------


class TestFindCandidates:
    def test_builds_status_filter(self, ec2):
        ec2.describe_volumes.return_value = {"Volumes": []}
        gc.find_candidates(ec2, [], grace_days=0)
        args, kwargs = ec2.describe_volumes.call_args
        filters = kwargs["Filters"]
        assert {"Name": "status", "Values": ["available"]} in filters

    def test_builds_tag_filters(self, ec2):
        ec2.describe_volumes.return_value = {"Volumes": []}
        gc.find_candidates(
            ec2,
            [("CostCenter", "Lab"), ("Project", "cost-detective")],
            grace_days=0,
        )
        filters = ec2.describe_volumes.call_args.kwargs["Filters"]
        assert {"Name": "tag:CostCenter", "Values": ["Lab"]} in filters
        assert {"Name": "tag:Project", "Values": ["cost-detective"]} in filters

    def test_skips_volumes_younger_than_grace(self, ec2):
        young = _vol("vol-young", age_days=1)
        old = _vol("vol-old", age_days=30)
        ec2.describe_volumes.return_value = {"Volumes": [young, old]}

        result = gc.find_candidates(ec2, [], grace_days=7)

        assert [v["VolumeId"] for v in result] == ["vol-old"]

    def test_zero_grace_includes_today(self, ec2):
        # Created "just now" — grace_days=0 includes it.
        now = datetime.now(timezone.utc)
        vol = _vol("vol-fresh", age_days=0)
        # _vol sets CreateTime to now - 0 days = now; nudge older by 1ms so cutoff > created
        vol["CreateTime"] = now - timedelta(milliseconds=1)
        ec2.describe_volumes.return_value = {"Volumes": [vol]}

        result = gc.find_candidates(ec2, [], grace_days=0, now=now)

        assert len(result) == 1


# ---------------------------------------------------------------------------
# Snapshot + delete
# ---------------------------------------------------------------------------


class TestSnapshotAndDelete:
    def test_snapshot_carries_source_tags(self, ec2):
        ec2.create_snapshot.return_value = {"SnapshotId": "snap-123"}
        vol = _vol("vol-aaa", tags=[("CostCenter", "Lab")])

        snap_id = gc.snapshot_volume(ec2, vol)

        assert snap_id == "snap-123"
        call_kwargs = ec2.create_snapshot.call_args.kwargs
        assert call_kwargs["VolumeId"] == "vol-aaa"
        tags = call_kwargs["TagSpecifications"][0]["Tags"]
        assert {"Key": "CostCenter", "Value": "Lab"} in tags
        assert {"Key": "PreDeleteSnapshot", "Value": "true"} in tags
        assert {"Key": "SourceVolumeId", "Value": "vol-aaa"} in tags

    def test_delete_calls_api(self, ec2):
        gc.delete_volume(ec2, "vol-aaa")
        ec2.delete_volume.assert_called_once_with(VolumeId="vol-aaa")


# ---------------------------------------------------------------------------
# run() — end-to-end dispatcher
# ---------------------------------------------------------------------------


class TestRun:
    def _opts(self, **kw):
        defaults = dict(
            region="eu-west-1",
            tag_filters=[("CostCenter", "Lab")],
            grace_days=0,
            delete=False,
            snapshot_first=False,
        )
        defaults.update(kw)
        return GcOptions(**defaults)

    def test_dry_run_default(self, ec2):
        ec2.describe_volumes.return_value = {
            "Volumes": [_vol("vol-aaa", tags=[("CostCenter", "Lab")])]
        }
        buf = io.StringIO()
        rc = gc.run(self._opts(), ec2_client=ec2, stdout=buf)

        assert rc == 0
        ec2.delete_volume.assert_not_called()
        ec2.create_snapshot.assert_not_called()
        assert "DRY-RUN" in buf.getvalue()
        assert "vol-aaa" in buf.getvalue()

    def test_refuses_delete_without_tag_filter(self, ec2):
        buf = io.StringIO()
        rc = gc.run(
            self._opts(tag_filters=[], delete=True), ec2_client=ec2, stdout=buf
        )
        assert rc == 2
        ec2.describe_volumes.assert_not_called()
        assert "requires at least one --tag" in buf.getvalue()

    def test_real_delete_no_snapshot(self, ec2):
        ec2.describe_volumes.return_value = {
            "Volumes": [_vol("vol-aaa", tags=[("CostCenter", "Lab")])]
        }
        buf = io.StringIO()
        rc = gc.run(self._opts(delete=True), ec2_client=ec2, stdout=buf)

        assert rc == 0
        ec2.create_snapshot.assert_not_called()
        ec2.delete_volume.assert_called_once_with(VolumeId="vol-aaa")
        assert "deleted  vol-aaa" in buf.getvalue()

    def test_real_delete_with_snapshot(self, ec2):
        ec2.describe_volumes.return_value = {
            "Volumes": [_vol("vol-aaa", tags=[("CostCenter", "Lab")])]
        }
        ec2.create_snapshot.return_value = {"SnapshotId": "snap-xyz"}
        buf = io.StringIO()
        rc = gc.run(
            self._opts(delete=True, snapshot_first=True),
            ec2_client=ec2,
            stdout=buf,
        )

        assert rc == 0
        ec2.create_snapshot.assert_called_once()
        ec2.delete_volume.assert_called_once_with(VolumeId="vol-aaa")
        output = buf.getvalue()
        assert "snap-xyz" in output
        assert "deleted  vol-aaa" in output

    def test_no_matches(self, ec2):
        ec2.describe_volumes.return_value = {"Volumes": []}
        buf = io.StringIO()
        rc = gc.run(self._opts(), ec2_client=ec2, stdout=buf)

        assert rc == 0
        assert "No matching" in buf.getvalue()

    def test_delete_failure_returns_nonzero(self, ec2):
        ec2.describe_volumes.return_value = {
            "Volumes": [
                _vol("vol-aaa", tags=[("CostCenter", "Lab")]),
                _vol("vol-bbb", tags=[("CostCenter", "Lab")]),
            ]
        }
        ec2.delete_volume.side_effect = [None, RuntimeError("boom")]
        buf = io.StringIO()
        rc = gc.run(self._opts(delete=True), ec2_client=ec2, stdout=buf)

        assert rc == 1
        assert "FAILED" in buf.getvalue()

    def test_tag_filter_prevents_account_wide_delete(self, ec2):
        # Even with --delete, the run() guard requires tag_filters.
        ec2.describe_volumes.return_value = {
            "Volumes": [_vol("vol-aaa")]  # untagged
        }
        buf = io.StringIO()
        rc = gc.run(
            self._opts(tag_filters=[], delete=True),
            ec2_client=ec2,
            stdout=buf,
        )
        assert rc == 2
        ec2.delete_volume.assert_not_called()
