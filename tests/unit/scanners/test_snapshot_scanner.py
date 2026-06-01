"""Tests for EBS snapshot scanner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.python.models import Finding
from src.python.scanners.snapshot import SnapshotScanner

SNAPSHOT_COST_PER_GB_MONTH = 0.05


@pytest.fixture
def mock_ec2_client():
    """Create a mock EC2 client."""
    return MagicMock()


@pytest.fixture
def mock_state_store():
    """Create a mock state store."""
    return MagicMock()


class TestSnapshotScannerSkipConditions:
    """Tests for snapshot scanner skip conditions."""

    def test_skips_snapshot_with_opt_out_tag(self, mock_ec2_client, mock_state_store):
        """Should skip snapshots with cloudsweep:opt-out=true tag."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=60),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [{"Key": "cloudsweep:opt-out", "Value": "true"}],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_snapshot_with_env_production_tag(
        self, mock_ec2_client, mock_state_store
    ):
        """Should skip snapshots with env=production tag."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=60),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [{"Key": "env", "Value": "production"}],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_snapshot_already_in_state(self, mock_ec2_client, mock_state_store):
        """Should skip snapshots already in state table (idempotency)."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=60),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = {"resource_id": "snap-123"}

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_snapshot_referenced_by_ami(self, mock_ec2_client, mock_state_store):
        """Should skip snapshots referenced by an AMI (Description contains ami-)."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=60),
            "VolumeSize": 100,
            "Description": "Created by CreateImage for ami-12345678",
            "Tags": [],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_snapshot_within_retention_period(
        self, mock_ec2_client, mock_state_store
    ):
        """Should skip snapshots created within retention period."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=10),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0


class TestSnapshotScannerFindingGeneration:
    """Tests for snapshot scanner finding generation."""

    def test_generates_finding_for_orphaned_snapshot(
        self, mock_ec2_client, mock_state_store
    ):
        """Should generate finding for orphaned snapshot older than retention."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=60),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        finding = findings[0]
        assert isinstance(finding, Finding)
        assert finding.resource_id == "snap-123"
        assert finding.resource_type == "snapshot"
        assert finding.region == "us-east-1"
        assert finding.idle_days == 60
        assert finding.size_gb == 100

    def test_calculates_correct_monthly_savings(
        self, mock_ec2_client, mock_state_store
    ):
        """Should calculate correct savings at $0.05/GB/month."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=60),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        expected_savings = 100 * SNAPSHOT_COST_PER_GB_MONTH
        assert findings[0].estimated_monthly_savings == expected_savings

    def test_includes_tags_in_finding(self, mock_ec2_client, mock_state_store):
        """Should include snapshot tags in finding."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=60),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [
                {"Key": "Name", "Value": "test-snapshot"},
                {"Key": "Environment", "Value": "dev"},
            ],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="eu-west-1")

        assert len(findings) == 1
        assert findings[0].tags == {"Name": "test-snapshot", "Environment": "dev"}

    def test_scans_multiple_snapshots(self, mock_ec2_client, mock_state_store):
        """Should find multiple orphaned snapshots."""
        snapshots = [
            {
                "SnapshotId": "snap-1",
                "State": "completed",
                "StartTime": datetime.now(UTC) - timedelta(days=60),
                "VolumeSize": 50,
                "Description": "Created by CreateSnapshots",
                "Tags": [],
            },
            {
                "SnapshotId": "snap-2",
                "State": "completed",
                "StartTime": datetime.now(UTC) - timedelta(days=90),
                "VolumeSize": 200,
                "Description": "Created by CreateSnapshots",
                "Tags": [],
            },
        ]
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": snapshots}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 2
        assert {f.resource_id for f in findings} == {"snap-1", "snap-2"}

    def test_mixed_snapshots_only_orphaned_reported(
        self, mock_ec2_client, mock_state_store
    ):
        """Should only report orphaned snapshots, skipping AMI-linked and recent."""
        snapshots = [
            {
                "SnapshotId": "snap-orphaned",
                "State": "completed",
                "StartTime": datetime.now(UTC) - timedelta(days=60),
                "VolumeSize": 100,
                "Description": "Created by CreateSnapshots",
                "Tags": [],
            },
            {
                "SnapshotId": "snap-ami-linked",
                "State": "completed",
                "StartTime": datetime.now(UTC) - timedelta(days=60),
                "VolumeSize": 200,
                "Description": "Created by CreateImage for ami-12345",
                "Tags": [],
            },
            {
                "SnapshotId": "snap-recent",
                "State": "completed",
                "StartTime": datetime.now(UTC) - timedelta(days=10),
                "VolumeSize": 150,
                "Description": "Created by CreateSnapshots",
                "Tags": [],
            },
        ]
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": snapshots}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].resource_id == "snap-orphaned"


class TestSnapshotScannerRetentionDays:
    """Tests for snapshot retention days configuration."""

    def test_respects_default_retention_days(self, mock_ec2_client, mock_state_store):
        """Should use default retention days from settings (30)."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=25),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_custom_retention_days(self, mock_ec2_client, mock_state_store):
        """Should respect custom retention days."""
        snapshot = {
            "SnapshotId": "snap-123",
            "State": "completed",
            "StartTime": datetime.now(UTC) - timedelta(days=15),
            "VolumeSize": 100,
            "Description": "Created by CreateSnapshots",
            "Tags": [],
        }
        mock_ec2_client.describe_snapshots.return_value = {"Snapshots": [snapshot]}
        mock_state_store.get_item.return_value = None

        scanner = SnapshotScanner(
            ec2_client=mock_ec2_client,
            state_store=mock_state_store,
            retention_days=10,
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1


class TestSnapshotCostRate:
    """Tests for snapshot cost rate."""

    def test_snapshot_cost_rate(self):
        """EBS snapshots should cost $0.05/GB/month."""
        assert SNAPSHOT_COST_PER_GB_MONTH == 0.05
