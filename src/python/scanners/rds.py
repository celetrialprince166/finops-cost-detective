"""RDS idle instance scanner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..config import settings
from ..models import Finding
from ..state import StateStore, today_iso

INSTANCE_CLASS_RATES = {
    "db.t3.micro": 12.0,
    "db.t3.small": 24.0,
    "db.t3.medium": 48.0,
    "db.t3.large": 96.0,
    "db.t3.xlarge": 192.0,
    "db.t3.2xlarge": 384.0,
    "db.m5.large": 86.0,
    "db.m5.xlarge": 173.0,
    "db.m5.2xlarge": 346.0,
    "db.m5.4xlarge": 692.0,
    "db.m5.12xlarge": 2076.0,
    "db.m5.24xlarge": 4152.0,
    "db.m6g.large": 86.0,
    "db.m6g.xlarge": 173.0,
    "db.m6g.2xlarge": 346.0,
    "db.r5.large": 115.0,
    "db.r5.xlarge": 230.0,
    "db.r5.2xlarge": 460.0,
    "db.r5.4xlarge": 920.0,
    "db.r6g.large": 115.0,
    "db.r6g.xlarge": 230.0,
    "db.r6g.2xlarge": 460.0,
}

DEFAULT_RATE = 15.0


class RDSScanner:
    """Scan for idle RDS instances with zero connections."""

    def __init__(
        self,
        rds_client=None,
        state_store: StateStore | None = None,
        idle_days: int | None = None,
        cloudwatch_client=None,
    ) -> None:
        self._rds = rds_client
        self._state = state_store or StateStore()
        self._idle_days = idle_days if idle_days is not None else settings.rds_idle_days
        self._cloudwatch = cloudwatch_client

    def scan(self, region: str) -> list[Finding]:
        """Scan for idle RDS instances."""
        findings: list[Finding] = []
        now = datetime.now(UTC)

        response = self._rds.describe_db_instances(MaxRecords=100)

        for instance in response.get("DBInstances", []):
            if self._should_skip(instance, now):
                continue

            finding = self._create_finding(instance, now, region)
            findings.append(finding)
            self._write_to_state(finding)

        return findings

    def _has_active_connections(self, instance_id: str, now: datetime) -> bool:
        """Check CloudWatch DatabaseConnections metric.

        Returns True if the instance has had any connections during the idle
        window (meaning it is active and should be skipped).  Returns False
        when there are no datapoints or all datapoints show Sum == 0, which
        means the instance is idle.
        """
        if self._cloudwatch is None:
            # No CloudWatch client available — treat as idle (conservative path
            # that keeps the finding).
            return False

        start_time = now - timedelta(days=self._idle_days)
        try:
            response = self._cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="DatabaseConnections",
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": instance_id}],
                StartTime=start_time,
                EndTime=now,
                Period=86400,
                Statistics=["Sum"],
            )
        except Exception:
            # On any CloudWatch error, treat as idle so we don't silently miss
            # real idle instances.
            return False

        datapoints = response.get("Datapoints", [])
        if not datapoints:
            return False  # No data → treat as idle

        return any(dp.get("Sum", 0) > 0 for dp in datapoints)

    def _should_skip(self, instance: dict, now: datetime) -> bool:
        tags = {t["Key"]: t["Value"] for t in instance.get("TagList", [])}

        if tags.get("cloudsweep:opt-out", "").lower() == "true":
            return True
        if tags.get("env", "").lower() == "production":
            return True
        if instance.get("DeletionProtection", False):
            return True
        if self._state.get_item(instance["DBInstanceIdentifier"], today_iso()):
            return True

        if instance.get("DBInstanceStatus") != "available":
            return True

        if instance.get("DBInstanceIdentifier") is None:
            return True

        instance_id = instance["DBInstanceIdentifier"]

        if self._has_active_connections(instance_id, now):
            return True

        return False

    def _write_to_state(self, finding: Finding) -> None:
        """Write finding to DynamoDB state table."""
        try:
            self._state.put_item(
                {
                    "resource_id": finding.resource_id,
                    "scan_date": today_iso(),
                    "resource_type": finding.resource_type,
                    "region": finding.region,
                    "estimated_monthly_savings": str(finding.estimated_monthly_savings),
                    "status": "found",
                }
            )
        except Exception:
            pass

    def _create_finding(self, instance: dict, now: datetime, region: str) -> Finding:
        tags = {t["Key"]: t["Value"] for t in instance.get("TagList", [])}
        size_gb = float(instance.get("AllocatedStorage", 0))
        instance_class = instance.get("DBInstanceClass", "unknown")
        rate = INSTANCE_CLASS_RATES.get(instance_class, DEFAULT_RATE)

        create_time_str = instance.get("InstanceCreateTime", "")
        if create_time_str:
            create_time = datetime.fromisoformat(create_time_str.replace("Z", "+00:00"))
            idle_days = (now.date() - create_time.date()).days
        else:
            idle_days = 0

        return Finding(
            resource_id=instance["DBInstanceIdentifier"],
            resource_type="rds",
            region=region,
            estimated_monthly_savings=round(rate, 2),
            idle_days=idle_days,
            size_gb=size_gb,
            instance_class=instance_class,
            tags=tags,
        )
