"""Unit tests for approval.py — Slack callback handler (Phase 4).

Tests the API Gateway Lambda handler: signature validation, approve path,
deny path, stale-timestamp rejection, and DynamoDB audit writes.

All boto3 calls are patched so no real AWS credentials are required.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import MagicMock, call, patch
from urllib import parse as urllib_parse

import pytest


# ---------------------------------------------------------------------------
# Helpers for building valid test events
# ---------------------------------------------------------------------------

TEST_SIGNING_SECRET = "test-signing-secret-abc123"


def _make_slack_body(action_id: str, task_token: str, resource_id: str, user: str = "kwame.ops") -> str:
    """Return a URL-encoded Slack interactive payload body."""
    value = json.dumps({"task_token": task_token, "resource_id": resource_id})
    payload_obj = {
        "type": "block_actions",
        "user": {"id": "U12345", "name": user},
        "actions": [
            {
                "action_id": action_id,
                "value": value,
            }
        ],
    }
    return urllib_parse.urlencode({"payload": json.dumps(payload_obj)})


def _make_event(
    action_id: str,
    task_token: str,
    resource_id: str,
    *,
    signing_secret: str = TEST_SIGNING_SECRET,
    timestamp: int | None = None,
    bad_signature: bool = False,
) -> dict[str, Any]:
    """Build an API Gateway event dict with a valid (or deliberately bad) Slack signature."""
    ts = timestamp if timestamp is not None else int(time.time())
    body = _make_slack_body(action_id, task_token, resource_id)

    sig_base = f"v0:{ts}:{body}"
    sig = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_base.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    if bad_signature:
        # Corrupt the signature so validation fails.
        sig = sig[:-4] + "XXXX"

    return {
        "headers": {
            "X-Slack-Request-Timestamp": str(ts),
            "X-Slack-Signature": sig,
        },
        "body": body,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_ssm_secret():
    """Patch SSM so _get_ssm_parameter returns TEST_SIGNING_SECRET."""
    with patch("src.python.approval._get_ssm_parameter", return_value=TEST_SIGNING_SECRET):
        yield


@pytest.fixture()
def mock_dynamodb_table():
    """Return a mock DynamoDB Table that records put_item calls."""
    table = MagicMock()
    table.put_item.return_value = {}
    with patch("src.python.approval.boto3") as mock_boto:
        resource_mock = MagicMock()
        resource_mock.Table.return_value = table
        mock_boto.resource.return_value = resource_mock
        # Also stub boto3.client for SFN — return a separate mock.
        sfn_mock = MagicMock()
        mock_boto.client.return_value = sfn_mock
        yield table, sfn_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestApprovalHandler:
    """Tests for the approval.handler API Gateway entry-point."""

    def test_valid_signature_approve(self, mock_ssm_secret, mock_dynamodb_table):
        """Valid HMAC + action=approve → send_task_success called with correct token."""
        from src.python.approval import handler

        table, sfn = mock_dynamodb_table
        task_token = "TOKEN-ABC-001"
        event = _make_event("approve", task_token, "vol-0abc123")

        response = handler(event, {})

        assert response["statusCode"] == 200
        sfn.send_task_success.assert_called_once()
        call_kwargs = sfn.send_task_success.call_args.kwargs
        assert call_kwargs["taskToken"] == task_token
        output = json.loads(call_kwargs["output"])
        assert output["approved"] is True
        assert output["approved_by"] == "kwame.ops"

    def test_valid_signature_deny(self, mock_ssm_secret, mock_dynamodb_table):
        """Valid HMAC + action=deny → send_task_failure called."""
        from src.python.approval import handler

        table, sfn = mock_dynamodb_table
        task_token = "TOKEN-DENY-002"
        event = _make_event("deny", task_token, "rds-instance-01")

        response = handler(event, {})

        assert response["statusCode"] == 200
        sfn.send_task_failure.assert_called_once()
        call_kwargs = sfn.send_task_failure.call_args.kwargs
        assert call_kwargs["taskToken"] == task_token
        assert call_kwargs["error"] == "Denied"
        assert "kwame.ops" in call_kwargs["cause"]

    def test_invalid_signature(self, mock_ssm_secret):
        """Tampered HMAC → handler returns 403 Forbidden."""
        from src.python.approval import handler

        event = _make_event("approve", "TOKEN-BAD", "vol-badtoken", bad_signature=True)
        response = handler(event, {})

        assert response["statusCode"] == 403
        assert response["body"] == "Forbidden"

    def test_stale_timestamp(self, mock_ssm_secret):
        """Timestamp older than 5 minutes → handler returns 403 (replay guard)."""
        from src.python.approval import handler

        stale_ts = int(time.time()) - 400  # 400 seconds ago — beyond 300 s limit
        event = _make_event(
            "approve",
            "TOKEN-STALE",
            "vol-stale",
            timestamp=stale_ts,
        )
        response = handler(event, {})

        assert response["statusCode"] == 403
        assert response["body"] == "Forbidden"

    def test_approve_writes_audit_record(self, mock_ssm_secret, mock_dynamodb_table):
        """Approve path → DynamoDB put_item called with decision='approve' and required fields."""
        from src.python.approval import handler

        table, sfn = mock_dynamodb_table
        resource_id = "vol-0auditcheck"
        event = _make_event("approve", "TOKEN-AUDIT-A", resource_id)

        handler(event, {})

        table.put_item.assert_called_once()
        item = table.put_item.call_args.kwargs["Item"]
        assert item["resource_id"] == resource_id
        assert item["decision"] == "approve"
        assert item["approved_by"] == "kwame.ops"
        assert "decision_timestamp" in item
        assert "scan_date" in item

    def test_deny_writes_audit_record(self, mock_ssm_secret, mock_dynamodb_table):
        """Deny path → DynamoDB put_item called with decision='deny' and required fields."""
        from src.python.approval import handler

        table, sfn = mock_dynamodb_table
        resource_id = "rds-0denieddb"
        event = _make_event("deny", "TOKEN-AUDIT-D", resource_id)

        handler(event, {})

        table.put_item.assert_called_once()
        item = table.put_item.call_args.kwargs["Item"]
        assert item["resource_id"] == resource_id
        assert item["decision"] == "deny"
        assert item["approved_by"] == "kwame.ops"
        assert "decision_timestamp" in item
        assert "scan_date" in item
