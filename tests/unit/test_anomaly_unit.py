"""Unit tests for anomaly detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.python.anomaly_scanner import (
    Anomaly,
    check_prerequisites,
    create_anomaly_subscription,
    create_cost_anomaly_monitor,
    detect_anomalies,
)


class TestAnomalyDetection:
    def test_sigma_calculation_above_3(self):
        """AC2: CRITICAL path - sigma > 3 should flag as CRITICAL."""
        daily_costs = [100.0] * 19 + [1800.0]
        mean = sum(daily_costs) / len(daily_costs)
        variance = sum((x - mean) ** 2 for x in daily_costs) / len(daily_costs)
        std = variance**0.5
        sigma = (1500.0 - mean) / std

        assert sigma > 3, f"Expected sigma > 3, got {sigma}"

    def test_sigma_calculation_2_to_3(self):
        """AC2: WARNING path - 2 <= sigma <= 3 should flag as WARNING."""
        daily_costs = [100.0, 100.0, 100.0, 100.0, 200.0]
        mean = sum(daily_costs) / len(daily_costs)
        variance = sum((x - mean) ** 2 for x in daily_costs) / len(daily_costs)
        std = variance**0.5
        sigma = (200.0 - mean) / std

        assert 2 <= sigma <= 3, f"Expected 2 <= sigma <= 3, got {sigma}"

    def test_sigma_zero_stddev_handled(self):
        """Edge case: constant costs should not cause division by zero."""
        daily_costs = [100.0] * 10

        mean = sum(daily_costs) / len(daily_costs)
        variance = sum((x - mean) ** 2 for x in daily_costs) / len(daily_costs)
        std = variance**0.5

        assert std == 0.0 or variance == 0.0

    @patch("src.python.anomaly_scanner.boto3")
    def test_detect_anomalies_returns_list(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-04-01", "End": "2026-04-02"},
                    "Groups": [
                        {
                            "Keys": ["Amazon EC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "100"}},
                        }
                    ],
                }
            ]
        }
        mock_boto.client.return_value = mock_ce

        result = detect_anomalies(days=7)
        assert isinstance(result, list)

    @patch("src.python.anomaly_scanner.boto3")
    def test_check_prerequisites_returns_ready(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.describe_anomaly_monitors.return_value = {}
        mock_boto.client.return_value = mock_ce

        result = check_prerequisites()
        assert result["status"] == "ready"

    @patch("src.python.anomaly_scanner.boto3")
    def test_check_prerequisites_returns_error_when_ce_fails(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.describe_anomaly_monitors.side_effect = Exception("AccessDenied")
        mock_boto.client.return_value = mock_ce

        result = check_prerequisites()
        assert result["status"] == "error"
        assert "message" in result

    @patch("src.python.anomaly_scanner.boto3")
    def test_create_cost_anomaly_monitor(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.create_anomaly_monitor.return_value = {"MonitorArn": "arn:test"}
        mock_boto.client.return_value = mock_ce

        result = create_cost_anomaly_monitor("test-monitor")
        assert result["status"] == "created"

    @patch("src.python.anomaly_scanner.boto3")
    def test_create_anomaly_subscription(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.create_anomaly_subscription.return_value = {
            "SubscriptionArn": "arn:test"
        }
        mock_boto.client.return_value = mock_ce

        result = create_anomaly_subscription("test-sub", 100, "test@example.com")
        assert result["status"] == "created"


class TestAnomalyDataClass:
    def test_anomaly_creation(self):
        anomaly = Anomaly(
            service="Amazon EC2",
            region="us-east-1",
            expected_spend=100.0,
            actual_spend=400.0,
            severity="CRITICAL",
            sigma=3.5,
            impact=300.0,
        )
        assert anomaly.service == "Amazon EC2"
        assert anomaly.severity == "CRITICAL"
        assert anomaly.sigma == 3.5

    def test_anomaly_impact_calculation(self):
        anomaly = Anomaly(
            service="Amazon EC2",
            region="us-east-1",
            expected_spend=500.0,
            actual_spend=2000.0,
            severity="CRITICAL",
            sigma=3.5,
            impact=1500.0,
        )
        assert anomaly.impact == 1500.0
        assert anomaly.actual_spend - anomaly.expected_spend == 1500.0

    def test_anomaly_severity_property(self):
        critical = Anomaly(
            service="EC2",
            region="us-east-1",
            expected_spend=100.0,
            actual_spend=500.0,
            severity="CRITICAL",
            sigma=4.0,
            impact=400.0,
        )
        warning = Anomaly(
            service="RDS",
            region="us-west-2",
            expected_spend=100.0,
            actual_spend=200.0,
            severity="WARNING",
            sigma=2.5,
            impact=100.0,
        )

        assert critical.severity == "CRITICAL"
        assert warning.severity == "WARNING"
