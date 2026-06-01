"""Tests for Phase 4 approval workflow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.python.approval import create_approval_request, send_slack_approval_message
from src.python.models import Finding


class TestApprovalWorkflow:
    @patch("src.python.approval.boto3")
    def test_create_approval_request_with_mock(self, mock_boto):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=600.0,
            idle_days=30,
        )
        mock_client = MagicMock()
        mock_boto.client.return_value = mock_client
        mock_client.start_sync_execution.return_value = {"executionArn": "arn:test"}

        with patch("src.python.approval.settings") as mock_settings:
            mock_settings.approval_sfn_arn = (
                "arn:aws:states:us-east-1:123456789012:stateMachine:approval"
            )
            request = create_approval_request(finding)

        assert request.finding.resource_id == "vol-123"
        assert request.task_token is not None

    def test_send_slack_approval_message_builds_payload(self):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=500.0,
            idle_days=30,
            size_gb=100,
            tags={"Name": "test"},
        )

        result = send_slack_approval_message(finding, webhook_url=None)
        assert result is False
