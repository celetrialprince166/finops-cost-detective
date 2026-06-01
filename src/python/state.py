"""Shared DynamoDB state access layer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import boto3

from .config import settings


def _get_dynamodb():
    import boto3

    return boto3.resource("dynamodb", region_name=settings.aws_region)


def _get_table():
    return _get_dynamodb().Table(settings.state_table_name)


class StateStore:
    """Thin wrapper over the CloudSweep state table."""

    def __init__(self, table=None) -> None:
        self._table = table

    def _get_table(self):
        return self._table

    def put_item(self, item: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._get_table().put_item(Item=item)
        except Exception:
            return None

    def get_item(self, resource_id: str, scan_date: str) -> dict[str, Any] | None:
        try:
            response = self._get_table().get_item(
                Key={"resource_id": resource_id, "scan_date": scan_date}
            )
            return response.get("Item")
        except Exception:
            return None

    def get_item(self, resource_id: str, scan_date: str) -> dict[str, Any] | None:
        try:
            response = self._get_table().get_item(
                Key={"resource_id": resource_id, "scan_date": scan_date}
            )
            return response.get("Item")
        except Exception as e:
            return None


def today_iso() -> str:
    return datetime.now(UTC).date().isoformat()
