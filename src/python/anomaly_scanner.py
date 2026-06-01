"""Anomaly detection using AWS Cost Explorer and custom sigma detection."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import boto3

from .config import settings
from .state import StateStore, today_iso


@dataclass
class Anomaly:
    service: str
    region: str
    expected_spend: float
    actual_spend: float
    severity: str
    sigma: float
    impact: float


def detect_anomalies(days: int = 30) -> list[Anomaly]:
    ce = boto3.client("ce", region_name="us-east-1")

    start_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now(UTC).strftime("%Y-%m-%d")

    response = ce.get_cost_and_usage(
        TimePeriod={"Start": start_date, "End": end_date},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    daily_spend_by_service = _aggregate_by_service(response)

    anomalies = []
    for service, daily_costs in daily_spend_by_service.items():
        if len(daily_costs) < 2:
            continue

        mean_spend = statistics.mean(daily_costs)
        std_spend = statistics.stdev(daily_costs) if len(daily_costs) > 1 else 0

        if std_spend == 0:
            continue

        recent_spend = daily_costs[-1] if daily_costs else mean_spend
        sigma = (recent_spend - mean_spend) / std_spend if std_spend > 0 else 0
        impact = recent_spend - mean_spend

        if abs(sigma) > 3 or impact > 1000:
            severity = "CRITICAL"
        elif abs(sigma) > 2:
            severity = "WARNING"
        else:
            continue

        anomalies.append(
            Anomaly(
                service=service,
                region="global",
                expected_spend=round(mean_spend, 2),
                actual_spend=round(recent_spend, 2),
                severity=severity,
                sigma=round(abs(sigma), 2),
                impact=round(impact, 2),
            )
        )

    return anomalies


def _aggregate_by_service(response: dict) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}

    for day_result in response.get("ResultsByTime", []):
        for group in day_result.get("Groups", []):
            service = group.get("Keys", [""])[0]
            cost = float(
                group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)
            )

            if service not in result:
                result[service] = []
            result[service].append(cost)

    return result


def create_cost_anomaly_monitor(monitor_name: str = "cloudsweep-monitor") -> dict:
    ce = boto3.client("ce", region_name="us-east-1")

    try:
        monitor = ce.create_anomaly_monitor(
            MonitorName=monitor_name,
            MonitorType="DIMENSIONAL",
            MonitorDimensionList=["SERVICE", "REGION"],
        )
        return {"status": "created", "monitor": monitor}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_anomaly_subscription(
    subscription_name: str = "cloudsweep-alerts",
    threshold: float = 100.0,
    email: str | None = None,
) -> dict:
    ce = boto3.client("ce", region_name="us-east-1")

    subscribers = []
    if email:
        subscribers.append({"Type": "EMAIL", "Address": email})
    elif settings.slack_webhook_url:
        pass

    try:
        subscription = ce.create_anomaly_subscription(
            SubscriptionName=subscription_name,
            Threshold=threshold,
            Subscribers=subscribers
            if subscribers
            else [{"Type": "EMAIL", "Address": "team@example.com"}],
        )
        return {"status": "created", "subscription": subscription}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_prerequisites() -> dict:
    ce = boto3.client("ce", region_name="us-east-1")

    try:
        ce.describe_anomaly_monitors()
        return {
            "status": "ready",
            "message": "Cost Explorer and Anomaly Detection available",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
