"""Integration tests for Phase 5 anomaly detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import boto3
import pytest

from src.python.anomaly_scanner import (
    Anomaly,
    check_prerequisites,
    create_anomaly_subscription,
    create_cost_anomaly_monitor,
    detect_anomalies,
)


# ==============================================================================
# TestAnomalyDetectionIntegration
# ==============================================================================


class TestAnomalyDetectionIntegration:
    """Tests that use mocked boto3 clients."""

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
                            "Metrics": {"UnblendedCost": {"Amount": "100.0"}},
                        }
                    ],
                },
                {
                    "TimePeriod": {"Start": "2026-04-02", "End": "2026-04-03"},
                    "Groups": [
                        {
                            "Keys": ["Amazon EC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "150.0"}},
                        }
                    ],
                },
            ]
        }
        mock_boto.client.return_value = mock_ce

        result = detect_anomalies(days=7)
        assert isinstance(result, list)

    @patch("src.python.anomaly_scanner.boto3")
    def test_check_prerequisites_returns_ready(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.describe_anomaly_monitors.return_value = {"AnomalyMonitors": []}
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
        assert len(result["message"]) > 0

    @patch("src.python.anomaly_scanner.boto3")
    def test_create_cost_anomaly_monitor_creates(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.create_anomaly_monitor.return_value = {
            "MonitorArn": "arn:aws:ce:us-east-1:123456789012:monitor/test"
        }
        mock_boto.client.return_value = mock_ce

        result = create_cost_anomaly_monitor("test-monitor")
        assert result["status"] == "created"

    @patch("src.python.anomaly_scanner.boto3")
    def test_create_cost_anomaly_monitor_fails_gracefully(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.create_anomaly_monitor.side_effect = Exception("AccessDenied")
        mock_boto.client.return_value = mock_ce

        result = create_cost_anomaly_monitor("test-monitor")
        assert result["status"] == "error"

    @patch("src.python.anomaly_scanner.boto3")
    def test_create_anomaly_subscription_creates(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.create_anomaly_subscription.return_value = {
            "SubscriptionArn": "arn:aws:ce:us-east-1:123456789012:subscription/test"
        }
        mock_boto.client.return_value = mock_ce

        result = create_anomaly_subscription("test-sub", 100, "test@example.com")
        assert result["status"] == "created"

    @patch("src.python.anomaly_scanner.boto3")
    def test_create_anomaly_subscription_fails_gracefully(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.create_anomaly_subscription.side_effect = Exception("AccessDenied")
        mock_boto.client.return_value = mock_ce

        result = create_anomaly_subscription("test-sub", 100, "test@example.com")
        assert result["status"] == "error"


# ==============================================================================
# TestNotifierPayloads - AC3/AC4/AC5 field validation
# ==============================================================================


class TestNotifierPayloads:
    """Test notifier payload structures. Validates PRD AC3/AC4/AC5 fields."""

    def test_daily_summary_all_fields_present(self):
        """AC3: Daily summary includes annual savings, per-type counts, mode."""
        from src.python.notifier import _build_daily_summary

        summary = {
            "total_savings": 500.0,
            "resources_scanned": 10,
            "mode": "DRY-RUN",
            "ebs_savings": 200.0,
            "rds_savings": 250.0,
            "eip_savings": 30.0,
            "snapshot_savings": 20.0,
            "ebs_count": 3,
            "rds_count": 2,
            "eip_count": 4,
            "snapshot_count": 1,
            "remediated": [
                {
                    "resource_id": "vol-123",
                    "resource_type": "ebs",
                    "savings": 50.0,
                    "size_gb": 100,
                },
            ],
        }

        message = _build_daily_summary(summary)

        assert "blocks" in message
        header = message["blocks"][0]["text"]["text"]
        assert "Daily Report" in header

        fields_text = " ".join(
            f.get("text", "")
            for block in message["blocks"]
            for f in block.get("fields", [])
        )

        assert "Annual Savings" in fields_text
        assert "6000" in fields_text or "6000.0" in fields_text

        assert "DRY-RUN" in fields_text

        assert "EBS" in fields_text and "(3)" in fields_text
        assert "RDS" in fields_text and "(2)" in fields_text
        assert "EIP" in fields_text and "(4)" in fields_text

    def test_daily_summary_no_findings(self):
        """AC4: No findings message when remediated list is empty."""
        from src.python.notifier import _build_daily_summary

        summary = {
            "total_savings": 0.0,
            "resources_scanned": 5,
            "mode": "DRY-RUN",
            "ebs_savings": 0.0,
            "rds_savings": 0.0,
            "eip_savings": 0.0,
            "snapshot_savings": 0.0,
            "ebs_count": 0,
            "rds_count": 0,
            "eip_count": 0,
            "snapshot_count": 0,
            "remediated": [],
        }

        message = _build_daily_summary(summary)

        fields_text = " ".join(
            f.get("text", "")
            for block in message["blocks"]
            for f in block.get("fields", [])
        )

        assert "(0)" in fields_text

    def test_anomaly_alert_all_fields_present(self):
        """AC5: Anomaly alert includes service, region, expected/actual spend."""
        from src.python.notifier import _build_anomaly_alert

        anomaly = {
            "service": "Amazon EC2",
            "region": "us-east-1",
            "expected_spend": 500.0,
            "actual_spend": 2000.0,
            "severity": "CRITICAL",
        }

        message = _build_anomaly_alert(anomaly)

        assert "blocks" in message
        header = message["blocks"][0]["text"]["text"]
        assert "CRITICAL" in header

        fields_text = " ".join(
            f.get("text", "")
            for block in message["blocks"]
            for f in block.get("fields", [])
        )

        assert "Amazon EC2" in fields_text
        assert "us-east-1" in fields_text
        assert "500" in fields_text
        assert "2000" in fields_text

    def test_anomaly_alert_warning_severity(self):
        """AC5: WARNING severity renders correctly."""
        from src.python.notifier import _build_anomaly_alert

        anomaly = {
            "service": "Amazon RDS",
            "region": "us-west-2",
            "expected_spend": 200.0,
            "actual_spend": 350.0,
            "severity": "WARNING",
        }

        message = _build_anomaly_alert(anomaly)

        header = message["blocks"][0]["text"]["text"]
        assert "WARNING" in header

    def test_no_findings_payload(self):
        from src.python.notifier import _build_no_findings_message

        message = _build_no_findings_message()

        assert "text" in message
        assert "No waste detected" in message["text"]

    def test_complete_message_payload(self):
        from src.python.notifier import _build_complete_message

        result = {"count": 5, "results": [{"resource_id": "vol-1"}]}
        message = _build_complete_message(result)

        assert "text" in message
        assert (
            "remediated" in message["text"].lower()
            or "resource" in message["text"].lower()
        )


# ==============================================================================
# TestAnomalyDataClass
# ==============================================================================


class TestAnomalyDataClass:
    def test_anomaly_severity_classification_critical(self):
        critical_anomaly = Anomaly(
            service="Amazon EC2",
            region="us-east-1",
            expected_spend=100.0,
            actual_spend=1500.0,
            severity="CRITICAL",
            sigma=4.0,
            impact=1400.0,
        )
        assert critical_anomaly.severity == "CRITICAL"
        assert critical_anomaly.sigma > 3

    def test_anomaly_severity_classification_warning(self):
        warning_anomaly = Anomaly(
            service="Amazon RDS",
            region="us-west-2",
            expected_spend=200.0,
            actual_spend=350.0,
            severity="WARNING",
            sigma=2.5,
            impact=150.0,
        )
        assert warning_anomaly.severity == "WARNING"
        assert 2 <= warning_anomaly.sigma <= 3

    def test_anomaly_fields_match_ac5(self):
        anomaly = Anomaly(
            service="Amazon EC2",
            region="us-east-1",
            expected_spend=500.0,
            actual_spend=2000.0,
            severity="CRITICAL",
            sigma=3.5,
            impact=1500.0,
        )

        assert hasattr(anomaly, "service")
        assert hasattr(anomaly, "region")
        assert hasattr(anomaly, "expected_spend")
        assert hasattr(anomaly, "actual_spend")
        assert hasattr(anomaly, "severity")

    def test_multiple_anomaly_creation(self):
        anomalies = [
            Anomaly(
                service="Amazon EC2",
                region="us-east-1",
                expected_spend=100.0,
                actual_spend=400.0,
                severity="CRITICAL",
                sigma=3.0,
                impact=300.0,
            ),
            Anomaly(
                service="Amazon RDS",
                region="us-west-2",
                expected_spend=200.0,
                actual_spend=350.0,
                severity="WARNING",
                sigma=2.5,
                impact=150.0,
            ),
        ]

        assert len(anomalies) == 2
        critical_count = sum(1 for a in anomalies if a.severity == "CRITICAL")
        warning_count = sum(1 for a in anomalies if a.severity == "WARNING")
        assert critical_count == 1
        assert warning_count == 1


# ==============================================================================
# TestNotifierEventTypes - Handler routing with CORRECTED mocks
# ==============================================================================


class TestNotifierEventTypes:
    """Test handler routes different event types correctly."""

    def test_handler_routes_daily_summary(self):
        """CRITICAL FIX: SSM mock must return str, not dict."""
        from src.python.notifier import handler

        with (
            patch("src.python.notifier._get_ssm_parameter") as mock_ssm,
            patch("src.python.notifier._post_to_slack") as mock_post,
        ):
            mock_ssm.return_value = "https://hooks.slack.com/services/test"
            mock_post.return_value = True

            event = {
                "event_type": "DAILY_SUMMARY",
                "summary": {
                    "total_savings": 100.0,
                    "resources_scanned": 5,
                    "mode": "DRY-RUN",
                },
            }

            result = handler(event, None)

            assert result["statusCode"] == 200
            mock_post.assert_called_once()

    def test_handler_routes_anomaly_alert(self):
        """CRITICAL FIX: SSM mock must return str, not dict."""
        from src.python.notifier import handler

        with (
            patch("src.python.notifier._get_ssm_parameter") as mock_ssm,
            patch("src.python.notifier._post_to_slack") as mock_post,
        ):
            mock_ssm.return_value = "https://hooks.slack.com/services/test"
            mock_post.return_value = True

            event = {
                "event_type": "ANOMALY_ALERT",
                "anomaly": {
                    "service": "EC2",
                    "region": "us-east-1",
                    "expected_spend": 100,
                    "actual_spend": 500,
                    "severity": "CRITICAL",
                },
            }

            result = handler(event, None)

            assert result["statusCode"] == 200

    def test_handler_routes_no_findings(self):
        """CRITICAL FIX: SSM mock must return str, not dict."""
        from src.python.notifier import handler

        with (
            patch("src.python.notifier._get_ssm_parameter") as mock_ssm,
            patch("src.python.notifier._post_to_slack") as mock_post,
        ):
            mock_ssm.return_value = "https://hooks.slack.com/services/test"
            mock_post.return_value = True

            event = {"event_type": "NO_FINDINGS"}

            result = handler(event, None)

            assert result["statusCode"] == 200


# ==============================================================================
# TestSigmaThresholds - AC2 integration test
# ==============================================================================


class TestSigmaThresholds:
    """AC2: Integration test with fabricated CE data to verify sigma thresholds."""

    @patch("src.python.anomaly_scanner.boto3")
    def test_sigma_gt_3_produces_critical(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {
                        "Start": f"2026-04-{day:02d}",
                        "End": f"2026-04-{day + 1:02d}",
                    },
                    "Groups": [
                        {
                            "Keys": ["Amazon EC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "100"}},
                        }
                    ],
                }
                for day in range(1, 30)
            ]
            + [
                {
                    "TimePeriod": {"Start": "2026-04-30", "End": "2026-05-01"},
                    "Groups": [
                        {
                            "Keys": ["Amazon EC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "1500"}},
                        }
                    ],
                }
            ]
        }
        mock_boto.client.return_value = mock_ce

        anomalies = detect_anomalies(days=30)

        ec2_anomaly = next((a for a in anomalies if a.service == "Amazon EC2"), None)
        assert ec2_anomaly is not None
        assert ec2_anomaly.severity == "CRITICAL", (
            f"Expected CRITICAL, got {ec2_anomaly.severity}"
        )

    @patch("src.python.anomaly_scanner.boto3")
    def test_sigma_2_to_3_produces_warning(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {
                        "Start": f"2026-04-{day:02d}",
                        "End": f"2026-04-{day + 1:02d}",
                    },
                    "Groups": [
                        {
                            "Keys": ["Amazon RDS"],
                            "Metrics": {"UnblendedCost": {"Amount": "100"}},
                        }
                    ],
                }
                for day in range(1, 6)
            ]
            + [
                {
                    "TimePeriod": {"Start": "2026-04-06", "End": "2026-04-07"},
                    "Groups": [
                        {
                            "Keys": ["Amazon RDS"],
                            "Metrics": {"UnblendedCost": {"Amount": "200"}},
                        }
                    ],
                }
            ]
        }
        mock_boto.client.return_value = mock_ce

        anomalies = detect_anomalies(days=6)

        rds_anomaly = next((a for a in anomalies if a.service == "Amazon RDS"), None)
        assert rds_anomaly is not None
        assert rds_anomaly.severity == "WARNING", (
            f"Expected WARNING, got {rds_anomaly.severity}"
        )

    @patch("src.python.anomaly_scanner.boto3")
    def test_impact_above_1000_produces_critical(self, mock_boto):
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {
                        "Start": f"2026-04-{day:02d}",
                        "End": f"2026-04-{day + 1:02d}",
                    },
                    "Groups": [
                        {
                            "Keys": ["Amazon S3"],
                            "Metrics": {"UnblendedCost": {"Amount": "500"}},
                        }
                    ],
                }
                for day in range(1, 29)
            ]
            + [
                {
                    "TimePeriod": {"Start": "2026-04-29", "End": "2026-04-30"},
                    "Groups": [
                        {
                            "Keys": ["Amazon S3"],
                            "Metrics": {"UnblendedCost": {"Amount": "2500"}},
                        }
                    ],
                }
            ]
        }
        mock_boto.client.return_value = mock_ce

        anomalies = detect_anomalies(days=30)

        s3_anomaly = next((a for a in anomalies if a.service == "Amazon S3"), None)
        assert s3_anomaly is not None
        assert s3_anomaly.impact >= 1000
        assert s3_anomaly.severity == "CRITICAL", (
            f"Expected CRITICAL, got {s3_anomaly.severity}"
        )
