"""Tests for EBS unattached volume scanner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.python.models import Finding
from src.python.scanners.ebs import EBSScanner, VOLUME_TYPE_RATES


@pytest.fixture
def mock_ec2_client():
    return MagicMock()


@pytest.fixture
def mock_state_store():
    return MagicMock()


class TestEBSScannerSkipConditions:
    def test_skips_volume_with_opt_out_tag(self, mock_ec2_client, mock_state_store):
        volume = {
            "VolumeId": "vol-123",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=30),
            "Size": 100,
            "VolumeType": "gp3",
            "Tags": [{"Key": "cloudsweep:opt-out", "Value": "true"}],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_volume_with_env_production_tag(
        self, mock_ec2_client, mock_state_store
    ):
        volume = {
            "VolumeId": "vol-123",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=30),
            "Size": 100,
            "VolumeType": "gp3",
            "Tags": [{"Key": "env", "Value": "production"}],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_volume_already_in_state(self, mock_ec2_client, mock_state_store):
        volume = {
            "VolumeId": "vol-123",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=30),
            "Size": 100,
            "VolumeType": "gp3",
            "Tags": [],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = {"resource_id": "vol-123"}

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_attached_volume(self, mock_ec2_client, mock_state_store):
        mock_ec2_client.describe_volumes.return_value = {"Volumes": []}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_volume_within_grace_period(self, mock_ec2_client, mock_state_store):
        volume = {
            "VolumeId": "vol-123",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=3),
            "Size": 100,
            "VolumeType": "gp3",
            "Tags": [],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(
            ec2_client=mock_ec2_client, state_store=mock_state_store, grace_days=7
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0


class TestEBSScannerFindingGeneration:
    def test_generates_finding_for_unattached_volume(
        self, mock_ec2_client, mock_state_store
    ):
        volume = {
            "VolumeId": "vol-123",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=30),
            "Size": 100,
            "VolumeType": "gp3",
            "Tags": [],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        finding = findings[0]
        assert isinstance(finding, Finding)
        assert finding.resource_id == "vol-123"
        assert finding.resource_type == "ebs"
        assert finding.region == "us-east-1"
        assert finding.idle_days == 30
        assert finding.size_gb == 100
        assert finding.volume_type == "gp3"

    def test_calculates_correct_monthly_savings_gp3(
        self, mock_ec2_client, mock_state_store
    ):
        volume = {
            "VolumeId": "vol-123",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=30),
            "Size": 100,
            "VolumeType": "gp3",
            "Tags": [],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].estimated_monthly_savings == 8.0

    def test_calculates_correct_monthly_savings_io1(
        self, mock_ec2_client, mock_state_store
    ):
        volume = {
            "VolumeId": "vol-456",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=30),
            "Size": 500,
            "VolumeType": "io1",
            "Tags": [],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].estimated_monthly_savings == 62.5

    def test_includes_tags_in_finding(self, mock_ec2_client, mock_state_store):
        volume = {
            "VolumeId": "vol-123",
            "State": "available",
            "CreateTime": datetime.now(UTC) - timedelta(days=30),
            "Size": 100,
            "VolumeType": "gp3",
            "Tags": [
                {"Key": "Name", "Value": "test-volume"},
                {"Key": "Environment", "Value": "dev"},
            ],
        }
        mock_ec2_client.describe_volumes.return_value = {"Volumes": [volume]}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="eu-west-1")

        assert len(findings) == 1
        assert findings[0].tags == {"Name": "test-volume", "Environment": "dev"}

    def test_scans_multiple_volumes(self, mock_ec2_client, mock_state_store):
        volumes = [
            {
                "VolumeId": "vol-1",
                "State": "available",
                "CreateTime": datetime.now(UTC) - timedelta(days=30),
                "Size": 50,
                "VolumeType": "gp3",
                "Tags": [],
            },
            {
                "VolumeId": "vol-2",
                "State": "available",
                "CreateTime": datetime.now(UTC) - timedelta(days=60),
                "Size": 200,
                "VolumeType": "gp3",
                "Tags": [],
            },
        ]
        mock_ec2_client.describe_volumes.return_value = {"Volumes": volumes}
        mock_state_store.get_item.return_value = None

        scanner = EBSScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 2
        assert {f.resource_id for f in findings} == {"vol-1", "vol-2"}


class TestEBSCostRates:
    GP3_RATE = 0.08
    IO1_RATE = 0.125
    GP2_RATE = 0.10
    SC1_RATE = 0.025
    ST1_RATE = 0.045

    def test_ebs_gp3_rate(self):
        assert self.GP3_RATE == 0.08

    def test_ebs_io1_rate(self):
        assert self.IO1_RATE == 0.125

    def test_ebs_gp2_rate(self):
        assert self.GP2_RATE == 0.10

    def test_ebs_sc1_rate(self):
        assert self.SC1_RATE == 0.025

    def test_ebs_st1_rate(self):
        assert self.ST1_RATE == 0.045
