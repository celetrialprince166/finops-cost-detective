"""Shared configuration for CloudSweep Lambda functions."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list_env(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("POWERTOOLS_SERVICE_NAME", "cloudsweep")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    dry_run: bool = _bool_env("CLOUDSWEEP_DRY_RUN", True)
    ebs_grace_days: int = int(os.getenv("EBS_GRACE_DAYS", "7"))
    rds_idle_days: int = int(os.getenv("RDS_IDLE_DAYS", "7"))
    snapshot_retention_days: int = int(os.getenv("SNAPSHOT_RETENTION_DAYS", "30"))
    approval_threshold_usd: float = float(os.getenv("APPROVAL_THRESHOLD_USD", "500"))
    state_table_name: str = os.getenv("STATE_TABLE_NAME", "cloudsweep-state")
    approval_sfn_arn: str = os.getenv("APPROVAL_SFN_ARN", "")
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    slack_webhook_parameter_name: str = os.getenv(
        "SLACK_WEBHOOK_PARAMETER_NAME",
        "/cloudsweep/slack/webhook",
    )
    slack_signing_secret_parameter_name: str = os.getenv(
        "SLACK_SIGNING_SECRET_PARAMETER_NAME",
        "/cloudsweep/slack/signing-secret",
    )
    scan_regions: list[str] = field(
        default_factory=lambda: _list_env(
            "SCAN_REGIONS", os.getenv("AWS_REGION", "us-east-1")
        )
    )


settings = Settings()
