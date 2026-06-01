"""Tests for RDS idle instance scanner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.python.models import Finding
from src.python.scanners.rds import RDSScanner


@pytest.fixture
def mock_rds_client():
    """Create a mock RDS client."""
    return MagicMock()


@pytest.fixture
def mock_state_store():
    """Create a mock state store."""
    mock = MagicMock()
    mock.get_item.return_value = None
    return mock


@pytest.fixture
def mock_cloudwatch_client():
    """Create a mock CloudWatch client."""
    return MagicMock()


class TestRDSScannerSkipConditions:
    """Tests for RDS scanner skip conditions."""

    def test_skips_instance_with_opt_out_tag(self, mock_rds_client, mock_state_store):
        """Should skip instances with cloudsweep:opt-out=true tag."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[{"Key": "cloudsweep:opt-out", "Value": "true"}],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_instance_with_env_production_tag(
        self, mock_rds_client, mock_state_store
    ):
        """Should skip instances with env=production tag."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[{"Key": "env", "Value": "production"}],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_instance_with_deletion_protection(
        self, mock_rds_client, mock_state_store
    ):
        """Should skip instances with DeletionProtection=true."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=True,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_instance_already_in_state(self, mock_rds_client, mock_state_store):
        """Should skip instances already in state table (idempotency)."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = {"resource_id": "db-123"}

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_instance_within_grace_period(
        self, mock_rds_client, mock_state_store, mock_cloudwatch_client
    ):
        """Should skip instances with recent CloudWatch connections (within idle_days window)."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=3),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [{"Sum": 10.0}]
        }

        scanner = RDSScanner(
            rds_client=mock_rds_client,
            state_store=mock_state_store,
            cloudwatch_client=mock_cloudwatch_client,
            idle_days=7,
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_instance_with_non_available_status(
        self, mock_rds_client, mock_state_store
    ):
        """Should skip instances that are not in 'available' status."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="stopped",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_skips_stopped_instance(self, mock_rds_client, mock_state_store):
        """Should skip instances that are stopped."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="stopped",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0


class TestRDSScannerFindingGeneration:
    """Tests for RDS scanner finding generation."""

    def test_generates_finding_for_idle_instance(
        self, mock_rds_client, mock_state_store
    ):
        """Should generate finding for idle RDS instance older than grace period."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        finding = findings[0]
        assert isinstance(finding, Finding)
        assert finding.resource_id == "db-123"
        assert finding.resource_type == "rds"
        assert finding.region == "us-east-1"
        assert finding.idle_days == 30
        assert finding.size_gb == 100
        assert finding.instance_class == "db.t3.micro"

    def test_calculates_correct_monthly_savings_t3_micro(
        self, mock_rds_client, mock_state_store
    ):
        """Should calculate correct savings for db.t3.micro."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].estimated_monthly_savings == 12.0

    def test_calculates_correct_monthly_savings_t3_small(
        self, mock_rds_client, mock_state_store
    ):
        """Should calculate correct savings for db.t3.small."""
        instance = _make_rds_instance(
            db_instance_identifier="db-456",
            db_instance_class="db.t3.small",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].estimated_monthly_savings == 24.0

    def test_calculates_correct_monthly_savings_t3_medium(
        self, mock_rds_client, mock_state_store
    ):
        """Should calculate correct savings for db.t3.medium."""
        instance = _make_rds_instance(
            db_instance_identifier="db-789",
            db_instance_class="db.t3.medium",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].estimated_monthly_savings == 48.0

    def test_includes_tags_in_finding(self, mock_rds_client, mock_state_store):
        """Should include instance tags in finding."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[
                {"Key": "Name", "Value": "test-db"},
                {"Key": "Environment", "Value": "dev"},
            ],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="eu-west-1")

        assert len(findings) == 1
        assert findings[0].tags == {"Name": "test-db", "Environment": "dev"}

    def test_scans_multiple_instances(self, mock_rds_client, mock_state_store):
        """Should find multiple idle RDS instances."""
        instances = [
            _make_rds_instance(
                db_instance_identifier="db-1",
                db_instance_class="db.t3.micro",
                allocated_storage=50,
                db_instance_status="available",
                deletion_protection=False,
                tags=[],
                create_time=datetime.now(UTC) - timedelta(days=30),
            ),
            _make_rds_instance(
                db_instance_identifier="db-2",
                db_instance_class="db.t3.small",
                allocated_storage=100,
                db_instance_status="available",
                deletion_protection=False,
                tags=[],
                create_time=datetime.now(UTC) - timedelta(days=60),
            ),
        ]
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": instances}
        mock_state_store.get_item.return_value = None

        scanner = RDSScanner(rds_client=mock_rds_client, state_store=mock_state_store)
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 2
        assert {f.resource_id for f in findings} == {"db-1", "db-2"}

    def test_uses_default_grace_period_from_settings(
        self, mock_rds_client, mock_state_store, mock_cloudwatch_client
    ):
        """Should use settings.rds_idle_days as default CloudWatch query window."""
        instance = _make_rds_instance(
            db_instance_identifier="db-123",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=5),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [{"Sum": 10.0}]
        }

        scanner = RDSScanner(
            rds_client=mock_rds_client,
            state_store=mock_state_store,
            cloudwatch_client=mock_cloudwatch_client,
            idle_days=7,
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0


class TestRDSScannerCloudWatchIdle:
    """Tests for CloudWatch DatabaseConnections idle detection."""

    def test_idle_instance_all_zero_datapoints(
        self, mock_rds_client, mock_state_store, mock_cloudwatch_client
    ):
        """Instance with all-zero DatabaseConnections should be flagged as idle."""
        instance = _make_rds_instance(
            db_instance_identifier="db-idle",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None
        # All datapoints have Sum == 0 → idle
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Sum": 0.0, "Timestamp": datetime.now(UTC)},
                {"Sum": 0.0, "Timestamp": datetime.now(UTC)},
            ]
        }

        scanner = RDSScanner(
            rds_client=mock_rds_client,
            state_store=mock_state_store,
            cloudwatch_client=mock_cloudwatch_client,
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].resource_id == "db-idle"

    def test_active_instance_sum_gt_zero_is_skipped(
        self, mock_rds_client, mock_state_store, mock_cloudwatch_client
    ):
        """Instance with DatabaseConnections Sum > 0 should be skipped (not idle)."""
        instance = _make_rds_instance(
            db_instance_identifier="db-active",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None
        # One datapoint has Sum > 0 → active
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Sum": 0.0, "Timestamp": datetime.now(UTC)},
                {"Sum": 5.0, "Timestamp": datetime.now(UTC)},
            ]
        }

        scanner = RDSScanner(
            rds_client=mock_rds_client,
            state_store=mock_state_store,
            cloudwatch_client=mock_cloudwatch_client,
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 0

    def test_no_datapoints_treated_as_idle(
        self, mock_rds_client, mock_state_store, mock_cloudwatch_client
    ):
        """Instance with no CloudWatch datapoints should be treated as idle."""
        instance = _make_rds_instance(
            db_instance_identifier="db-no-data",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None
        # Empty datapoints → no metric data → treat as idle
        mock_cloudwatch_client.get_metric_statistics.return_value = {"Datapoints": []}

        scanner = RDSScanner(
            rds_client=mock_rds_client,
            state_store=mock_state_store,
            cloudwatch_client=mock_cloudwatch_client,
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1
        assert findings[0].resource_id == "db-no-data"

    def test_cloudwatch_not_called_when_no_client(
        self, mock_rds_client, mock_state_store
    ):
        """When no CloudWatch client is provided, instance should still be flagged as idle."""
        instance = _make_rds_instance(
            db_instance_identifier="db-no-cw",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None

        # No cloudwatch_client → conservative: treat as idle
        scanner = RDSScanner(
            rds_client=mock_rds_client,
            state_store=mock_state_store,
        )
        findings = scanner.scan(region="us-east-1")

        assert len(findings) == 1

    def test_cloudwatch_called_with_correct_params(
        self, mock_rds_client, mock_state_store, mock_cloudwatch_client
    ):
        """CloudWatch should be called with the correct namespace, metric and dimensions."""
        instance = _make_rds_instance(
            db_instance_identifier="db-param-check",
            db_instance_class="db.t3.micro",
            allocated_storage=100,
            db_instance_status="available",
            deletion_protection=False,
            tags=[],
            create_time=datetime.now(UTC) - timedelta(days=30),
        )
        mock_rds_client.describe_db_instances.return_value = {"DBInstances": [instance]}
        mock_state_store.get_item.return_value = None
        mock_cloudwatch_client.get_metric_statistics.return_value = {"Datapoints": []}

        scanner = RDSScanner(
            rds_client=mock_rds_client,
            state_store=mock_state_store,
            cloudwatch_client=mock_cloudwatch_client,
            idle_days=7,
        )
        scanner.scan(region="us-east-1")

        call_kwargs = mock_cloudwatch_client.get_metric_statistics.call_args[1]
        assert call_kwargs["Namespace"] == "AWS/RDS"
        assert call_kwargs["MetricName"] == "DatabaseConnections"
        assert call_kwargs["Dimensions"] == [
            {"Name": "DBInstanceIdentifier", "Value": "db-param-check"}
        ]
        assert call_kwargs["Period"] == 86400
        assert "Sum" in call_kwargs["Statistics"]


class TestRDSInstanceClassRates:
    """Tests for RDS instance class rates."""

    T3_MICRO_RATE = 12.0
    T3_SMALL_RATE = 24.0
    T3_MEDIUM_RATE = 48.0

    def test_rds_db_t3_micro_rate(self):
        """RDS db.t3.micro should cost $12/month."""
        assert self.T3_MICRO_RATE == 12.0

    def test_rds_db_t3_small_rate(self):
        """RDS db.t3.small should cost $24/month."""
        assert self.T3_SMALL_RATE == 24.0

    def test_rds_db_t3_medium_rate(self):
        """RDS db.t3.medium should cost $48/month."""
        assert self.T3_MEDIUM_RATE == 48.0


def _make_rds_instance(
    db_instance_identifier: str,
    db_instance_class: str,
    allocated_storage: int,
    db_instance_status: str,
    deletion_protection: bool,
    tags: list[dict],
    create_time: datetime,
) -> dict:
    """Helper to create a mock RDS instance."""
    return {
        "DBInstanceIdentifier": db_instance_identifier,
        "DBInstanceClass": db_instance_class,
        "AllocatedStorage": allocated_storage,
        "DBInstanceStatus": db_instance_status,
        "DeletionProtection": deletion_protection,
        "TagList": tags,
        "InstanceCreateTime": create_time.isoformat(),
        "EnhancedMonitoringResourceArn": "",
        "DBInstanceArn": f"arn:aws:rds:us-east-1:123456789:db:{db_instance_identifier}",
    }
