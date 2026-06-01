"""Lambda entry points for CloudSweep.

lambda_handler  — Phase 1 smoke handler (smoke_lambda)
scan_handler    — Full scan orchestrator (scan_lambda): runs all 4 scanners
"""

from __future__ import annotations

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit

from .config import settings
from .scanners.ebs import EBSScanner
from .scanners.eip import EIPScanner
from .scanners.rds import RDSScanner
from .scanners.snapshot import SnapshotScanner

logger = Logger(service=settings.app_name, level=settings.log_level)
tracer = Tracer(service=settings.app_name)
metrics = Metrics(namespace="CloudSweep", service=settings.app_name)


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context) -> dict:
    """Phase 1 smoke handler — proves EventBridge → SFN → Lambda path works."""
    metrics.add_metric(name="ResourcesScanned", unit=MetricUnit.Count, value=0)
    logger.info("CloudSweep smoke handler invoked", extra={"dry_run": settings.dry_run})
    return {
        "status": "ok",
        "message": "CloudSweep smoke path executed",
        "dry_run": settings.dry_run,
        "event": event,
    }


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def scan_handler(event: dict, context) -> dict:
    """Scan orchestrator — runs all 4 resource scanners across configured regions.

    Returns a findings list consumed by the evaluate Lambda as the next SFN step.
    """
    all_findings = []

    for region in settings.scan_regions:
        logger.info("Scanning region", extra={"region": region})

        ec2 = boto3.client("ec2", region_name=region)
        rds_client = boto3.client("rds", region_name=region)
        cw = boto3.client("cloudwatch", region_name=region)

        scanners = [
            EBSScanner(ec2_client=ec2),
            RDSScanner(rds_client=rds_client, cloudwatch_client=cw),
            EIPScanner(ec2_client=ec2),
            SnapshotScanner(ec2_client=ec2),
        ]

        for scanner in scanners:
            try:
                findings = scanner.scan(region)
                all_findings.extend(findings)
                logger.info(
                    "Scanner complete",
                    extra={"scanner": type(scanner).__name__, "count": len(findings)},
                )
            except Exception as exc:
                logger.error(
                    "Scanner failed",
                    extra={"scanner": type(scanner).__name__, "error": str(exc)},
                )

    metrics.add_metric(
        name="ResourcesScanned", unit=MetricUnit.Count, value=len(all_findings)
    )

    logger.info("Scan complete", extra={"total_findings": len(all_findings)})

    return {
        "findings": [f.to_dict() for f in all_findings],
        "count": len(all_findings),
        "regions": settings.scan_regions,
        "dry_run": settings.dry_run,
    }
