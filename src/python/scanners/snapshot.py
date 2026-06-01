"""EBS snapshot scanner for orphaned snapshots."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from ..config import settings
from ..models import Finding
from ..state import StateStore, today_iso

SNAPSHOT_COST_PER_GB_MONTH = 0.05

AMI_DESCRIPTION_PATTERN = re.compile(r"Created by CreateImage for ami-")


class SnapshotScanner:
    """Scan for orphaned EBS snapshots not referenced by AMIs."""

    def __init__(
        self,
        ec2_client=None,
        state_store: StateStore | None = None,
        retention_days: int | None = None,
    ) -> None:
        self._ec2 = ec2_client
        self._state = state_store or StateStore()
        self._retention_days = (
            retention_days
            if retention_days is not None
            else settings.snapshot_retention_days
        )

    def scan(self, region: str) -> list[Finding]:
        """Scan for orphaned EBS snapshots."""
        findings: list[Finding] = []
        now = datetime.now(UTC)
        retention_cutoff = (now - timedelta(days=self._retention_days)).date()

        response = self._ec2.describe_snapshots(
            OwnerIds=["self"],
            MaxResults=100,
        )

        for snapshot in response.get("Snapshots", []):
            if self._should_skip(snapshot, retention_cutoff):
                continue

            finding = self._create_finding(snapshot, now, region)
            findings.append(finding)
            self._write_to_state(finding)

        return findings

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

    def _should_skip(self, snapshot: dict, retention_cutoff) -> bool:
        tags = {t["Key"]: t["Value"] for t in snapshot.get("Tags", [])}

        if tags.get("cloudsweep:opt-out", "").lower() == "true":
            return True
        if tags.get("env", "").lower() == "production":
            return True
        if self._state.get_item(snapshot["SnapshotId"], today_iso()):
            return True
        if self._is_referenced_by_ami(snapshot):
            return True

        start_date = snapshot["StartTime"].date()
        if start_date > retention_cutoff:
            return True

        return False

    def _is_referenced_by_ami(self, snapshot: dict) -> bool:
        description = snapshot.get("Description", "")
        return bool(AMI_DESCRIPTION_PATTERN.search(description))

    def _create_finding(self, snapshot: dict, now: datetime, region: str) -> Finding:
        tags = {t["Key"]: t["Value"] for t in snapshot.get("Tags", [])}
        size_gb = float(snapshot["VolumeSize"])
        idle_days = (now.date() - snapshot["StartTime"].date()).days

        return Finding(
            resource_id=snapshot["SnapshotId"],
            resource_type="snapshot",
            region=region,
            estimated_monthly_savings=round(size_gb * SNAPSHOT_COST_PER_GB_MONTH, 2),
            idle_days=idle_days,
            size_gb=size_gb,
            tags=tags,
        )
