"""Tests for EIP unattached (orphaned) scanner."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.python.models import Finding
from src.python.scanners.eip import EIPScanner


@pytest.fixture
def mock_ec2_client():
    """Create a mock EC2 client."""
    return MagicMock()


@pytest.fixture
def mock_state_store():
    """Create a mock state store."""
    return MagicMock()


class TestEIPScannerSkipConditions:
    """Tests for EIP scanner skip conditions."""

    def test_skips_eip_with_opt_out_tag(self, mock_ec2_client, mock_state_store):
        """Should skip EIPs with cloudsweep:opt-out=true tag."""
        eip = {
            "AllocationId": "eipalloc-123",
            "AssociationId": None,
            "Tags": [{"Key": "cloudsweep:opt-out", "Value": "true"}],
        }
        mock_ec2_client.describe_addresses.return_value = {"Addresses": [eip]}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_eip_already_in_state(self, mock_ec2_client, mock_state_store):
        """Should skip EIPs already in state table (idempotency)."""
        eip = {
            "AllocationId": "eipalloc-123",
            "AssociationId": None,
            "Tags": [],
        }
        mock_ec2_client.describe_addresses.return_value = {"Addresses": [eip]}
        mock_state_store.get_item.return_value = {"resource_id": "eipalloc-123"}

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_attached_eip(self, mock_ec2_client, mock_state_store):
        """Should skip EIPs that have an AssociationId (attached)."""
        eip = {
            "AllocationId": "eipalloc-123",
            "AssociationId": "eipassoc-123",
            "Tags": [],
        }
        mock_ec2_client.describe_addresses.return_value = {"Addresses": [eip]}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_when_no_eips(self, mock_ec2_client, mock_state_store):
        """Should return empty list when no EIPs exist."""
        mock_ec2_client.describe_addresses.return_value = {"Addresses": []}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0


class TestEIPScannerFindingGeneration:
    """Tests for EIP scanner finding generation."""

    def test_generates_finding_for_orphaned_eip(
        self, mock_ec2_client, mock_state_store
    ):
        """Should generate finding for orphaned EIP (no AssociationId)."""
        eip = {
            "AllocationId": "eipalloc-123",
            "AssociationId": None,
            "Tags": [],
        }
        mock_ec2_client.describe_addresses.return_value = {"Addresses": [eip]}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        finding = findings[0]
        assert isinstance(finding, Finding)
        assert finding.resource_id == "eipalloc-123"
        assert finding.resource_type == "eip"
        assert finding.region == "us-east-1"

    def test_calculates_correct_monthly_savings(
        self, mock_ec2_client, mock_state_store
    ):
        """Should calculate correct savings ($3.65/month per EIP)."""
        eip = {
            "AllocationId": "eipalloc-123",
            "AssociationId": None,
            "Tags": [],
        }
        mock_ec2_client.describe_addresses.return_value = {"Addresses": [eip]}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].estimated_monthly_savings == 3.65

    def test_includes_tags_in_finding(self, mock_ec2_client, mock_state_store):
        """Should include EIP tags in finding."""
        eip = {
            "AllocationId": "eipalloc-123",
            "AssociationId": None,
            "Tags": [
                {"Key": "Name", "Value": "test-eip"},
                {"Key": "Environment", "Value": "dev"},
            ],
        }
        mock_ec2_client.describe_addresses.return_value = {"Addresses": [eip]}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="eu-west-1")

        assert len(findings) == 1
        assert findings[0].tags == {"Name": "test-eip", "Environment": "dev"}

    def test_scans_multiple_orphaned_eips(self, mock_ec2_client, mock_state_store):
        """Should find multiple orphaned EIPs."""
        eips = [
            {
                "AllocationId": "eipalloc-1",
                "AssociationId": None,
                "Tags": [],
            },
            {
                "AllocationId": "eipalloc-2",
                "AssociationId": None,
                "Tags": [],
            },
        ]
        mock_ec2_client.describe_addresses.return_value = {"Addresses": eips}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 2
        assert {f.resource_id for f in findings} == {"eipalloc-1", "eipalloc-2"}

    def test_finds_only_orphaned_eips_mixed_with_attached(
        self, mock_ec2_client, mock_state_store
    ):
        """Should only find orphaned EIPs, filtering out attached ones."""
        eips = [
            {
                "AllocationId": "eipalloc-1",
                "AssociationId": "eipassoc-1",
                "Tags": [],
            },
            {
                "AllocationId": "eipalloc-2",
                "AssociationId": None,
                "Tags": [],
            },
            {
                "AllocationId": "eipalloc-3",
                "AssociationId": None,
                "Tags": [],
            },
        ]
        mock_ec2_client.describe_addresses.return_value = {"Addresses": eips}
        mock_state_store.get_item.return_value = None

        scanner = EIPScanner(ec2_client=mock_ec2_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 2
        assert {f.resource_id for f in findings} == {"eipalloc-2", "eipalloc-3"}


class TestEIPCostRate:
    """Tests for EIP cost rate."""

    EIP_MONTHLY_COST = 3.65

    def test_eip_monthly_cost(self):
        """EIP should cost $3.65/month."""
        assert self.EIP_MONTHLY_COST == 3.65
