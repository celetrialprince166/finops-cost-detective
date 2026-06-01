"""EBS unattached volume scanner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..config import settings
from ..models import Finding
from ..state import StateStore, today_iso

VOLUME_TYPE_RATES = {
    "gp3": 0.08,
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.025,
}


class EBSScanner:
    """Scan for unattached EBS volumes in 'available' state."""

    def __init__(
        self,
        ec2_client=None,
        state_store: StateStore | None = None,
        grace_days: int | None = None,
    ) -> None:
        self._ec2 = ec2_client
        self._state = state_store or StateStore()
        self._grace_days = (
            grace_days if grace_days is not None else settings.ebs_grace_days
        )

    def scan(self, region: str) -> list[Finding]:
        """Scan for unattached EBS volumes."""
        findings: list[Finding] = []
        now = datetime.now(UTC)
        grace_cutoff = (now - timedelta(days=self._grace_days)).date()

        response = self._ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}],
            MaxResults=100,
        )

        for volume in response.get("Volumes", []):
            if self._should_skip(volume, grace_cutoff):
                continue

            finding = self._create_finding(volume, now, region)
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

    def _should_skip(self, volume: dict, grace_cutoff) -> bool:
        tags = {t["Key"]: t["Value"] for t in volume.get("Tags", [])}

        if tags.get("cloudsweep:opt-out", "").lower() == "true":
            return True
        if tags.get("env", "").lower() == "production":
            return True
        if self._state.get_item(volume["VolumeId"], today_iso()):
            return True

        create_date = volume["CreateTime"].date()
        if create_date > grace_cutoff:
            return True

        return False

    def _create_finding(self, volume: dict, now: datetime, region: str) -> Finding:
        tags = {t["Key"]: t["Value"] for t in volume.get("Tags", [])}
        size_gb = float(volume["Size"])
        volume_type = volume["VolumeType"]
        rate = VOLUME_TYPE_RATES.get(volume_type, 0.10)
        idle_days = (now.date() - volume["CreateTime"].date()).days

        return Finding(
            resource_id=volume["VolumeId"],
            resource_type="ebs",
            region=region,
            estimated_monthly_savings=round(size_gb * rate, 2),
            idle_days=idle_days,
            size_gb=size_gb,
            volume_type=volume_type,
            tags=tags,
        )
