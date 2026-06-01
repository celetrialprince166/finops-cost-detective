"""Notifier Lambda — sends Slack Block Kit messages for approvals and summaries.

Handles the following ``event_type`` values dispatched by the Step Functions
state machine:

* ``NEEDS_APPROVAL``  — sends an interactive approval message with task token.
* ``COMPLETE``        — sends a remediation-complete summary.
* ``TIMEOUT``         — notifies that an approval request expired after 24 h.
* ``DENIED``          — notifies that remediation was denied.
* ``NO_FINDINGS``     — notifies that the scan found no waste.

Only stdlib and boto3 are used (``urllib.request``, ``urllib.parse``, ``json``).
"""

from __future__ import annotations

import json
from typing import Any
from urllib import request as urllib_request

import boto3

from .config import settings


# ---------------------------------------------------------------------------
# SSM helper
# ---------------------------------------------------------------------------


def _get_ssm_parameter(param_path: str) -> str:
    """Fetch a (SecureString) SSM Parameter Store value."""
    ssm = boto3.client("ssm", region_name=settings.aws_region)
    response = ssm.get_parameter(Name=param_path, WithDecryption=True)
    return response["Parameter"]["Value"]


# ---------------------------------------------------------------------------
# Slack posting helper
# ---------------------------------------------------------------------------


def _post_to_slack(webhook_url: str, message: dict) -> bool:
    """POST *message* as JSON to *webhook_url*.  Returns True on HTTP 200."""
    try:
        data = json.dumps(message).encode("utf-8")
        req = urllib_request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------


def _build_approval_message(task_token: str, findings: list[dict]) -> dict:
    """Build a Slack Block Kit message with Approve / Deny buttons.

    The button ``value`` carries a JSON object with ``task_token`` and
    ``resource_id`` so the API Gateway callback handler can resume the
    Step Functions workflow.
    """
    # Use the first finding's resource_id as the representative resource.
    primary_resource_id: str = findings[0].get("resource_id", "") if findings else ""
    button_value = json.dumps(
        {"task_token": task_token, "resource_id": primary_resource_id}
    )

    # Build per-finding fields
    finding_fields: list[dict] = []
    for f in findings:
        finding_fields.extend(
            [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*{f.get('resource_id', 'N/A')}*\n"
                        f"Type: {f.get('resource_type', 'N/A')} | "
                        f"Region: {f.get('region', 'N/A')} | "
                        f"Est. Savings: ${f.get('estimated_monthly_savings', 0):.2f}/mo"
                    ),
                }
            ]
        )

    blocks: list[dict] = [
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
                "text": "The following resources have been flagged for remediation:",
            },
        },
    ]

    if finding_fields:
        blocks.append({"type": "section", "fields": finding_fields})

    blocks.append(
        {
            "type": "actions",
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
        }
    )

    return {"blocks": blocks}


def _build_complete_message(remediation_result: dict) -> dict:
    count: int = remediation_result.get("count", 0)
    # Accept a list of results as well
    if isinstance(remediation_result.get("results"), list):
        count = len(remediation_result["results"])
    return {
        "text": (
            f":white_check_mark: Remediation complete: {count} resource(s) processed."
        )
    }


def _build_timeout_message() -> dict:
    return {
        "text": (
            ":hourglass_flowing_sand: Approval request timed out after 24 hours. "
            "No action taken."
        )
    }


def _build_denied_message(findings: list[dict], error: dict) -> dict:
    denied_ids = ", ".join(f.get("resource_id", "N/A") for f in findings)
    return {
        "text": (
            f":x: Remediation denied. No action taken."
            + (f"  Resources: {denied_ids}" if denied_ids else "")
        )
    }


def _build_no_findings_message() -> dict:
    return {"text": ":white_check_mark: CloudSweep scan complete. No waste detected."}


def _build_daily_summary(summary: dict) -> dict:
    total_savings = summary.get("total_savings", 0)
    resources_scanned = summary.get("resources_scanned", 0)
    mode = summary.get("mode", "DRY-RUN")
    ebs_savings = summary.get("ebs_savings", 0)
    rds_savings = summary.get("rds_savings", 0)
    eip_savings = summary.get("eip_savings", 0)
    snapshot_savings = summary.get("snapshot_savings", 0)
    ebs_count = summary.get("ebs_count", 0)
    rds_count = summary.get("rds_count", 0)
    eip_count = summary.get("eip_count", 0)
    snapshot_count = summary.get("snapshot_count", 0)
    remediated = summary.get("remediated", [])

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "CloudSweep Daily Report"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Total Savings:*\n${total_savings}/month"},
                {
                    "type": "mrkdwn",
                    "text": f"*Annual Savings:*\n${total_savings * 12}/year",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Resources Scanned:*\n{resources_scanned}",
                },
                {"type": "mrkdwn", "text": f"*Mode:*\n{mode}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Savings & Count by Resource Type:*"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*EBS:* ${ebs_savings} ({ebs_count})"},
                {"type": "mrkdwn", "text": f"*RDS:* ${rds_savings} ({rds_count})"},
                {"type": "mrkdwn", "text": f"*EIP:* ${eip_savings} ({eip_count})"},
                {
                    "type": "mrkdwn",
                    "text": f"*Snapshots:* ${snapshot_savings} ({snapshot_count})",
                },
            ],
        },
    ]

    if remediated:
        remediated_text = "\n".join(
            [
                f"• {r.get('resource_type', 'unknown')}: {r.get('resource_id', 'N/A')} - ${r.get('savings', 0)}"
                for r in remediated[:5]
            ]
        )
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Remediated:*\n{remediated_text}"},
            }
        )

    return {"blocks": blocks}


def _build_anomaly_alert(anomaly: dict) -> dict:
    severity = anomaly.get("severity", "WARNING")
    emoji = ":warning:" if severity == "WARNING" else ":rotating_light:"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Anomaly Detected - {severity}",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Service:*\n{anomaly.get('service', 'N/A')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Region:*\n{anomaly.get('region', 'N/A')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Expected:*\n${anomaly.get('expected_spend', 0)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Actual:*\n${anomaly.get('actual_spend', 0)}",
                },
            ],
        },
    ]

    return {"blocks": blocks}


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------


def handler(event: dict, context: Any) -> dict:
    """Dispatch a Slack notification based on ``event["event_type"]``.

    Expected event shapes (all routed from Step Functions states):

    NEEDS_APPROVAL:
        {"event_type": "NEEDS_APPROVAL", "task_token": "...", "findings": [...]}

    COMPLETE:
        {"event_type": "COMPLETE", "remediation_result": {...}}

    TIMEOUT:
        {"event_type": "TIMEOUT", "findings": [...]}

    DENIED:
        {"event_type": "DENIED", "findings": [...], "error": {...}}

    NO_FINDINGS:
        {"event_type": "NO_FINDINGS"}

    DAILY_SUMMARY:
        {"event_type": "DAILY_SUMMARY", "summary": {...}}

    ANOMALY_ALERT:
        {"event_type": "ANOMALY_ALERT", "anomaly": {...}}
    """
    webhook_url = _get_ssm_parameter(settings.slack_webhook_parameter_name)

    event_type: str = event.get("event_type", "")

    if event_type == "NEEDS_APPROVAL":
        task_token: str = event.get("task_token", "")
        findings: list[dict] = event.get("findings", [])
        message = _build_approval_message(task_token, findings)

    elif event_type == "COMPLETE":
        remediation_result: dict = event.get("remediation_result", {})
        message = _build_complete_message(remediation_result)

    elif event_type == "TIMEOUT":
        message = _build_timeout_message()

    elif event_type == "DENIED":
        findings = event.get("findings", [])
        error: dict = event.get("error", {})
        message = _build_denied_message(findings, error)

    elif event_type == "NO_FINDINGS":
        message = _build_no_findings_message()

    elif event_type == "DAILY_SUMMARY":
        summary = event.get("summary", {})
        message = _build_daily_summary(summary)

    elif event_type == "ANOMALY_ALERT":
        anomaly = event.get("anomaly", {})
        message = _build_anomaly_alert(anomaly)

    else:
        message = {"text": f":information_source: CloudSweep event: {event_type}"}

    ok = _post_to_slack(webhook_url, message)
    return {"statusCode": 200 if ok else 500, "sent": ok}
