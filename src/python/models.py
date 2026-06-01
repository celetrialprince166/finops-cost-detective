"""Domain models shared across scanners, evaluation, and remediation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Finding:
    resource_id: str
    resource_type: str
    region: str
    estimated_monthly_savings: float
    idle_days: int = 0
    size_gb: float | None = None
    tags: dict[str, str] = field(default_factory=dict)
    volume_type: str | None = None
    instance_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemediationResult:
    finding: Finding
    action: str
    status: str
    snapshot_id: str | None
    correlation_id: str
    dry_run: bool
    approved_by: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finding"] = self.finding.to_dict()
        return payload
