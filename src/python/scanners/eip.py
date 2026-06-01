"""EIP unattached (orphaned) scanner."""

from __future__ import annotations

from ..models import Finding
from ..state import StateStore, today_iso

EIP_MONTHLY_COST = 3.65


class EIPScanner:
    """Scan for orphaned Elastic IP addresses without AssociationId."""

    def __init__(
        self,
        ec2_client=None,
        state_store: StateStore | None = None,
    ) -> None:
        self._ec2 = ec2_client
        self._state = state_store or StateStore()

    def scan(self, region: str) -> list[Finding]:
        """Scan for orphaned EIPs (without AssociationId)."""
        findings: list[Finding] = []

        response = self._ec2.describe_addresses()

        for eip in response.get("Addresses", []):
            if self._should_skip(eip):
                continue

            finding = self._create_finding(eip, region)
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

    def _should_skip(self, eip: dict) -> bool:
        tags = {t["Key"]: t["Value"] for t in eip.get("Tags", [])}

        if tags.get("cloudsweep:opt-out", "").lower() == "true":
            return True
        if self._state.get_item(eip["AllocationId"], today_iso()):
            return True
        if eip.get("AssociationId"):
            return True

        return False

    def _create_finding(self, eip: dict, region: str) -> Finding:
        tags = {t["Key"]: t["Value"] for t in eip.get("Tags", [])}

        return Finding(
            resource_id=eip["AllocationId"],
            resource_type="eip",
            region=region,
            estimated_monthly_savings=EIP_MONTHLY_COST,
            tags=tags,
        )
