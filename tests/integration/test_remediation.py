"""Integration tests for the auto-remediation path using moto mock_aws.

Tests the full scan → evaluate → remediate pipeline for EBS volumes,
including idempotency on a second remediation attempt.

Run with: py -m pytest tests/integration/test_remediation.py -v
"""

from __future__ import annotations

import uuid

import boto3
import pytest
from moto import mock_aws

from src.python.evaluator import Classification, evaluate
from src.python.remediator import remediate
from src.python.scanners.ebs import EBSScanner
from src.python.state import StateStore, today_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_state_table(dynamodb_client) -> object:
    """Create a uniquely-named CloudSweep state table and return the Table resource."""
    table_name = f"cloudsweep-test-{uuid.uuid4().hex[:8]}"

    dynamodb_client.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "resource_id", "KeyType": "HASH"},
            {"AttributeName": "scan_date", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "resource_id", "AttributeType": "S"},
            {"AttributeName": "scan_date", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    return boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAutoRemediationPath:
    """Integration tests for the full scan → evaluate → remediate pipeline."""

    @mock_aws
    def test_full_ebs_auto_remediation_pipeline(self):
        """
        End-to-end test:
        1. Create mock EBS volume in 'available' state.
        2. EBSScanner finds it.
        3. evaluate() classifies it as AUTO_REMEDIATE.
        4. remediate() deletes the volume and records result.
        5. Second remediate() call is idempotent → already_processed.
        """
        region = "us-east-1"
        ec2 = boto3.client("ec2", region_name=region)
        dynamodb = boto3.client("dynamodb", region_name=region)

        # --- Step 1: Setup mock AWS resources ---
        vol = ec2.create_volume(
            Size=100,
            AvailabilityZone="us-east-1a",
            VolumeType="gp3",
        )
        volume_id = vol["VolumeId"]

        table = _create_state_table(dynamodb)
        store = StateStore(table=table)

        # --- Step 2: Scan ---
        scanner = EBSScanner(
            ec2_client=ec2,
            state_store=store,
            grace_days=0,
        )
        findings = scanner.scan(region)

        assert len(findings) >= 1
        finding = next(f for f in findings if f.resource_id == volume_id)
        assert finding.resource_type == "ebs"
        assert finding.region == region

        # --- Step 3: Evaluate ---
        classification = evaluate(finding)
        # EBS savings for 100 GB gp3 = 100 * 0.08 = $8, well below $500 threshold
        assert classification == Classification.AUTO_REMEDIATE

        # --- Step 4: Remediate ---
        result = remediate(finding, dry_run=False, state_store=store)

        assert result.status == "success"
        assert result.action == "deleted"
        assert result.snapshot_id is not None

        # --- Step 5: Idempotency — second call should be skipped ---
        result2 = remediate(finding, dry_run=False, state_store=store)

        assert result2.action == "skipped"
        assert result2.status == "already_processed"

    @mock_aws
    def test_remediation_dry_run_does_not_delete_volume(self):
        """Dry-run remediation should not delete the EBS volume."""
        region = "us-east-1"
        ec2 = boto3.client("ec2", region_name=region)
        dynamodb = boto3.client("dynamodb", region_name=region)

        vol = ec2.create_volume(
            Size=50,
            AvailabilityZone="us-east-1a",
            VolumeType="gp2",
        )
        volume_id = vol["VolumeId"]

        table = _create_state_table(dynamodb)
        store = StateStore(table=table)

        scanner = EBSScanner(
            ec2_client=ec2,
            state_store=store,
            grace_days=0,
        )
        findings = scanner.scan(region)
        finding = next(f for f in findings if f.resource_id == volume_id)

        result = remediate(finding, dry_run=True, state_store=store)

        assert result.status == "dry_run"
        # Volume should still exist
        vols = ec2.describe_volumes(VolumeIds=[volume_id])
        assert len(vols["Volumes"]) == 1

    @mock_aws
    def test_scan_writes_finding_to_state_table(self):
        """EBSScanner.scan() should persist findings to DynamoDB after scanning."""
        region = "us-east-1"
        ec2 = boto3.client("ec2", region_name=region)
        dynamodb = boto3.client("dynamodb", region_name=region)

        vol = ec2.create_volume(
            Size=20,
            AvailabilityZone="us-east-1a",
            VolumeType="gp3",
        )
        volume_id = vol["VolumeId"]

        table = _create_state_table(dynamodb)
        store = StateStore(table=table)

        scanner = EBSScanner(
            ec2_client=ec2,
            state_store=store,
            grace_days=0,
        )
        findings = scanner.scan(region)
        assert any(f.resource_id == volume_id for f in findings)

        # Confirm the item was written to DynamoDB
        item = store.get_item(volume_id, today_iso())
        assert item is not None
        assert item["resource_id"] == volume_id
        assert item["status"] == "found"
        assert item["resource_type"] == "ebs"
