"""Evaluator - classifies findings for remediation path."""

from __future__ import annotations

from .config import settings
from .models import Finding


class Classification:
    AUTO_REMEDIATE = "AUTO_REMEDIATE"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    SKIP = "SKIP"


def evaluate(finding: Finding) -> str:
    if finding.estimated_monthly_savings < settings.approval_threshold_usd:
        if finding.resource_type != "rds":
            return Classification.AUTO_REMEDIATE
    return Classification.NEEDS_APPROVAL


def evaluate_batch(findings: list[Finding]) -> dict[str, list[Finding]]:
    results = {
        Classification.AUTO_REMEDIATE: [],
        Classification.NEEDS_APPROVAL: [],
    }
    for finding in findings:
        results[evaluate(finding)].append(finding)
    return results


def handler(event: dict, context) -> dict:
    """Evaluate Lambda entry point — classifies scan findings for SFN routing.

    Receives the scan Lambda output (a findings list), classifies each finding,
    then returns a single decision for the Step Functions Choice state:

    - ``NEEDS_APPROVAL``  if any finding requires human review
    - ``AUTO_REMEDIATE``  if all findings can be auto-remediated
    - ``NO_FINDINGS``     if the scan found nothing
    """
    findings_dicts: list[dict] = event.get("findings", [])

    if not findings_dicts:
        return {
            "decision": Classification.SKIP,
            "findings": [],
            "auto_remediate_count": 0,
            "needs_approval_count": 0,
        }

    findings = [Finding(**f) for f in findings_dicts]
    batch = evaluate_batch(findings)

    needs_approval = batch[Classification.NEEDS_APPROVAL]
    auto_remediate = batch[Classification.AUTO_REMEDIATE]

    # Route the whole batch through approval if any finding needs it.
    # The remediator handles mixed batches; the SFN choice needs a single signal.
    if needs_approval:
        decision = Classification.NEEDS_APPROVAL
        routed_findings = [f.to_dict() for f in needs_approval + auto_remediate]
    elif auto_remediate:
        decision = Classification.AUTO_REMEDIATE
        routed_findings = [f.to_dict() for f in auto_remediate]
    else:
        decision = Classification.SKIP
        routed_findings = []

    return {
        "decision": decision,
        "findings": routed_findings,
        "auto_remediate_count": len(auto_remediate),
        "needs_approval_count": len(needs_approval),
        "dry_run": event.get("dry_run", True),
    }
