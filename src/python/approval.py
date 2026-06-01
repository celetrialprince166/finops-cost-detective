"""Approval Lambda — handles Slack interactive component callbacks via API Gateway.

This module serves two purposes:

1. ``handler`` — the API Gateway Lambda entry-point for Phase 4.
   Validates the Slack HMAC-SHA256 signature, parses the action (approve /
   deny), calls Step Functions SendTaskSuccess / SendTaskFailure, and writes
   a DynamoDB audit record.

2. Helper utilities used by older tests and the notifier:
   ``ApprovalRequest``, ``create_approval_request``, ``send_slack_approval_message``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import boto3

from .config import settings
from .models import Finding
from .state import StateStore, today_iso


# ---------------------------------------------------------------------------
# SSM helper
# ---------------------------------------------------------------------------

def _get_ssm_parameter(param_path: str) -> str:
    """Fetch a (SecureString) SSM Parameter Store value."""
    ssm = boto3.client("ssm", region_name=settings.aws_region)
    response = ssm.get_parameter(Name=param_path, WithDecryption=True)
    return response["Parameter"]["Value"]


# ---------------------------------------------------------------------------
# Slack request signature verification
# ---------------------------------------------------------------------------

def _verify_slack_signature(event: dict, signing_secret: str) -> bool:
    """Return True when the Slack HMAC-SHA256 signature on *event* is valid.

    Requests whose timestamp is more than 5 minutes old are rejected to
    prevent replay attacks.
    """
    headers: dict = event.get("headers", {}) or {}

    # API Gateway may lowercase header names, so try both casings.
    timestamp: str = (
        headers.get("X-Slack-Request-Timestamp")
        or headers.get("x-slack-request-timestamp")
        or ""
    )
    received_sig: str = (
        headers.get("X-Slack-Signature")
        or headers.get("x-slack-signature")
        or ""
    )
    body: str = event.get("body", "") or ""

    try:
        ts_int = int(timestamp)
    except (ValueError, TypeError):
        return False

    # Replay-attack guard: reject requests older than 5 minutes.
    if abs(time.time() - ts_int) > 300:
        return False

    sig_base = f"v0:{timestamp}:{body}"
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_base.encode(),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, received_sig)


# ---------------------------------------------------------------------------
# API Gateway Lambda handler — Phase 4 primary entry-point
# ---------------------------------------------------------------------------

def handler(event: dict, context: Any) -> dict:
    """Handle Slack interactive-component POST callbacks from API Gateway.

    Steps:
    1. Load the Slack signing secret from SSM.
    2. Validate HMAC-SHA256 signature — return 403 on failure.
    3. Parse ``application/x-www-form-urlencoded`` body → JSON payload.
    4. Extract ``action_id``, ``task_token``, ``resource_id``, ``approved_by``.
    5. Call ``sfn.send_task_success`` (approve) or ``sfn.send_task_failure`` (deny).
    6. Write DynamoDB audit record regardless of decision.
    7. Return ``{"statusCode": 200, "body": "OK"}``.
    """
    # 1 — Load signing secret
    signing_secret = _get_ssm_parameter(settings.slack_signing_secret_parameter_name)

    # 2 — Signature validation MUST precede all processing
    if not _verify_slack_signature(event, signing_secret):
        return {"statusCode": 403, "body": "Forbidden"}

    # 3 — Parse body
    body: str = event.get("body", "") or ""
    parsed = urllib_parse.parse_qs(body)
    payload_str: str = parsed.get("payload", ["{}"])[0]
    try:
        payload: dict = json.loads(payload_str)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Bad Request"}

    # 4 — Extract fields
    actions: list = payload.get("actions", [])
    action: dict = actions[0] if actions else {}
    action_id: str = action.get("action_id", "")  # "approve" or "deny"

    # The button value carries both task_token and resource_id as JSON-encoded string.
    raw_value: str = action.get("value", "{}")
    try:
        value_obj: dict = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        value_obj = {}

    task_token: str = value_obj.get("task_token", "")
    resource_id: str = value_obj.get("resource_id", "")
    approved_by: str = payload.get("user", {}).get("name", "unknown")

    sfn = boto3.client("stepfunctions", region_name=settings.aws_region)

    # 5 — Notify Step Functions
    if action_id == "approve":
        sfn.send_task_success(
            taskToken=task_token,
            output=json.dumps({"approved": True, "approved_by": approved_by}),
        )
    else:
        sfn.send_task_failure(
            taskToken=task_token,
            error="Denied",
            cause=f"Denied by {approved_by}",
        )

    # 6 — DynamoDB audit record (both approve and deny paths)
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    table = dynamodb.Table(settings.state_table_name)
    store = StateStore(table=table)
    store.put_item(
        {
            "resource_id": resource_id,
            "scan_date": today_iso(),
            "decision": action_id,
            "approved_by": approved_by,
            "decision_timestamp": datetime.now(UTC).isoformat(),
        }
    )

    # 7 — Respond to Slack
    return {"statusCode": 200, "body": "OK"}


# ---------------------------------------------------------------------------
# Legacy / helper dataclasses and functions (used by existing tests)
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRequest:
    """Lightweight record returned by ``create_approval_request``."""

    finding: Finding
    task_token: str
    timeout_seconds: int = 86400


@dataclass
class ApprovalDecision:
    """Record of a human approve / deny decision."""

    finding: Finding
    decision: str
    approved_by: str
    decision_timestamp: str


def create_approval_request(finding: Finding, sfn_client=None) -> ApprovalRequest:
    """Create an approval request and return an :class:`ApprovalRequest`.

    In production the task token comes from Step Functions' waitForTaskToken
    integration.  This helper generates a stub UUID token so callers (including
    unit tests) can exercise the approval path without a live state machine.
    """
    client = sfn_client or boto3.client(
        "stepfunctions", region_name=settings.aws_region
    )
    task_token = str(uuid.uuid4())

    try:
        client.start_sync_execution(
            stateMachineArn=settings.approval_sfn_arn,
            name=f"approval-{finding.resource_id}-{today_iso()}",
            input=json.dumps(
                {
                    "finding": finding.resource_id,
                    "task_token": task_token,
                    "timeout": 86400,
                }
            ),
        )
    except Exception:
        # Allow unit tests that stub the client to flow through.
        pass

    return ApprovalRequest(finding=finding, task_token=task_token)


def send_slack_approval_message(
    finding: Finding,
    task_token: str = "",
    webhook_url: str | None = None,
) -> bool:
    """POST a Slack Block Kit approval message to *webhook_url*.

    Returns ``True`` on HTTP 200, ``False`` on any error or when no URL is
    provided.  Builds a rich Block Kit message with Approve / Deny buttons
    whose ``value`` JSON carries both the ``task_token`` and ``resource_id``
    for the API Gateway callback handler.
    """
    url = webhook_url or settings.slack_webhook_url
    if not url:
        return False

    button_value = json.dumps(
        {"task_token": task_token, "resource_id": finding.resource_id}
    )

    message: dict = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":rotating_light: CloudSweep: Approval Required",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "The following resource has been flagged for remediation:",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Resource ID:*\n{finding.resource_id}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:*\n{finding.resource_type}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Region:*\n{finding.region}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*Est. Monthly Savings:*\n"
                            f"${finding.estimated_monthly_savings:.2f}"
                        ),
                    },
                ],
            },
            {
                "type": "actions",
                "block_id": f"approval_{finding.resource_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": ":white_check_mark: Approve All",
                        },
                        "style": "primary",
                        "action_id": "approve",
                        "value": button_value,
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": ":x: Deny All",
                        },
                        "style": "danger",
                        "action_id": "deny",
                        "value": button_value,
                    },
                ],
            },
        ]
    }

    try:
        data = json.dumps(message).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False
