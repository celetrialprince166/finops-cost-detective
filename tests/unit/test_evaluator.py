"""Tests for evaluator."""

from __future__ import annotations

import pytest

from src.python.evaluator import Classification, evaluate, evaluate_batch
from src.python.models import Finding


class TestEvaluatorClassification:
    def test_auto_remediate_below_threshold_non_rds(self):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=50.0,
        )
        assert evaluate(finding) == Classification.AUTO_REMEDIATE

    def test_needs_approval_above_threshold(self):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=600.0,
        )
        assert evaluate(finding) == Classification.NEEDS_APPROVAL

    def test_needs_approval_rds_any_amount(self):
        finding = Finding(
            resource_id="db-123",
            resource_type="rds",
            region="us-east-1",
            estimated_monthly_savings=50.0,
        )
        assert evaluate(finding) == Classification.NEEDS_APPROVAL

    def test_needs_approval_at_threshold(self):
        finding = Finding(
            resource_id="vol-123",
            resource_type="ebs",
            region="us-east-1",
            estimated_monthly_savings=500.0,
        )
        assert evaluate(finding) == Classification.NEEDS_APPROVAL

    def test_auto_remediate_eip(self):
        finding = Finding(
            resource_id="eip-123",
            resource_type="eip",
            region="us-east-1",
            estimated_monthly_savings=3.65,
        )
        assert evaluate(finding) == Classification.AUTO_REMEDIATE


class TestEvaluatorBatch:
    def test_batch_classification(self):
        findings = [
            Finding(
                resource_id="vol-1",
                resource_type="ebs",
                region="us-east-1",
                estimated_monthly_savings=50.0,
            ),
            Finding(
                resource_id="vol-2",
                resource_type="ebs",
                region="us-east-1",
                estimated_monthly_savings=600.0,
            ),
            Finding(
                resource_id="db-1",
                resource_type="rds",
                region="us-east-1",
                estimated_monthly_savings=12.0,
            ),
        ]
        results = evaluate_batch(findings)

        assert len(results[Classification.AUTO_REMEDIATE]) == 1
        assert len(results[Classification.NEEDS_APPROVAL]) == 2
