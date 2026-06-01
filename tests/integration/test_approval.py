"""Integration tests for Phase 4 approval workflow using moto."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from src.python.approval import create_approval_request, send_slack_approval_message
from src.python.models import Finding


@pytest.fixture
def dynamodb_table():
    import uuid

    table_name = f"cloudsweep-test-{uuid.uuid4().hex[:8]}"
    dynamodb = boto3.resource("dynamodb", "us-east-1")
    table = dynamodb.create_table(
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
    yield table
    try:
        table.delete()
    except Exception:
        pass


@pytest.fixture
def sfn_client():
    return boto3.client("stepfunctions", "us-east-1")


@mock_aws
class TestApprovalIntegration:
    def test_send_slack_approval_message_returns_false_without_webhook(self):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=600.0,
        )
        result = send_slack_approval_message(finding, webhook_url=None)
        assert result is False

    def test_send_slack_approval_message_returns_false_with_invalid_url(self):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=600.0,
        )
        result = send_slack_approval_message(
            finding, webhook_url="https://invalid.example.com"
        )
        assert result is False

    def test_create_approval_request_with_valid_sfn(self, sfn_client, dynamodb_table):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=600.0,
        )

        import unittest.mock as mock

        mock_settings = mock.MagicMock()
        mock_settings.approval_sfn_arn = (
            "arn:aws:states:us-east-1:123456789012:stateMachine:test"
        )

        with mock.patch("src.python.approval.settings", mock_settings):
            request = create_approval_request(finding, sfn_client=sfn_client)

        assert request.finding.resource_id == "vol-123"
