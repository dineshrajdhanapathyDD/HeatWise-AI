"""DynamoDB assessment store (Milestone 4, D-M4-6).

One item per record with exactly these attributes: report_id, entity, created_at,
location_key, request_json, report_json, duration_ms, plus `checklist_json` only while the
record has checklist progress (D-M5-9). Like the JSON store, a record holds only the request
(place, forecast days, community profile), the report and community-level checklist
progress; no personal data.

Checklist updates are read-modify-write (get_item, then update_item with
`attribute_exists(report_id)`); two concurrent updates to the same report are last write wins.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import boto3

from backend.api.schemas import AssessmentRequest
from backend.models.report import PreparednessReport
from backend.session import dynamodb_schema as schema
from backend.session.store import AssessmentRecord, AssessmentStore, apply_checklist_change

logger = logging.getLogger("heatwise.store.dynamodb")

_REPORT_ID = re.compile(r"^[0-9a-f]{32}$")


def _item_bytes(item: dict[str, dict[str, Any]]) -> int:
    size = 0
    for name, value in item.items():
        size += len(name.encode("utf-8"))
        for v in value.values():
            size += len(v.encode("utf-8")) if isinstance(v, str) else 1
    return size


class DynamoDbAssessmentStore(AssessmentStore):
    def __init__(self, table_name: str, client: Any = None, region_name: str | None = None) -> None:
        self.table_name = table_name
        self.client = client or boto3.client("dynamodb", region_name=region_name)

    # -- conversion ------------------------------------------------------------------------
    @staticmethod
    def _to_item(record: AssessmentRecord) -> dict[str, dict[str, Any]]:
        from backend.api.summaries import location_key

        duration = ({"N": repr(float(record.duration_ms))} if record.duration_ms is not None
                    else {"NULL": True})
        item = {
            schema.ASSESSMENTS_PK: {"S": record.report_id},
            schema.BY_CREATED_PK: {"S": schema.ENTITY},
            schema.CREATED_AT: {"S": schema.ts(record.created_at)},
            schema.BY_LOCATION_PK: {"S": location_key(record.report)},
            schema.ATTR_REQUEST: {"S": record.request.model_dump_json()},
            schema.ATTR_REPORT: {"S": record.report.model_dump_json()},
            schema.ATTR_DURATION: duration,
        }
        if record.checklist_completed:
            item[schema.ATTR_CHECKLIST] = {"S": DynamoDbAssessmentStore._checklist_json(record)}
        return item

    @staticmethod
    def _checklist_json(record: AssessmentRecord) -> str:
        return json.dumps({k: schema.ts(v) for k, v in record.checklist_completed.items()}, sort_keys=True)

    @staticmethod
    def _from_item(item: dict[str, dict[str, Any]]) -> AssessmentRecord | None:
        try:
            duration = item.get(schema.ATTR_DURATION, {"NULL": True})
            checklist = item.get(schema.ATTR_CHECKLIST)
            progress = ({k: schema.parse_ts(v) for k, v in json.loads(checklist["S"]).items()}
                        if checklist else {})
            return AssessmentRecord(
                report_id=item[schema.ASSESSMENTS_PK]["S"],
                created_at=schema.parse_ts(item[schema.CREATED_AT]["S"]),
                duration_ms=float(duration["N"]) if "N" in duration else None,
                request=AssessmentRequest.model_validate_json(item[schema.ATTR_REQUEST]["S"]),
                report=PreparednessReport.model_validate_json(item[schema.ATTR_REPORT]["S"]),
                checklist_completed=progress,
            )
        except (KeyError, ValueError, AttributeError):
            logger.warning("unreadable assessment item skipped: %s", item.get(schema.ASSESSMENTS_PK))
            return None

    def _query(self, limit: int | None = None, select_count: bool = False, **kwargs: Any):
        """Yield items (or page counts) of a paginated query, stopping after `limit` items."""
        params: dict[str, Any] = {"TableName": self.table_name, "ScanIndexForward": False, **kwargs}
        if select_count:
            params["Select"] = "COUNT"
        seen = 0
        while True:
            if limit is not None:
                params["Limit"] = max(limit - seen, 1)
            page = self.client.query(**params)
            if select_count:
                yield page["Count"]
            else:
                for item in page.get("Items", []):
                    yield item
                    seen += 1
                    if limit is not None and seen >= limit:
                        return
            if "LastEvaluatedKey" not in page:
                return
            params["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def _by_created(self, limit: int | None = None, select_count: bool = False):
        return self._query(limit, select_count, IndexName=schema.BY_CREATED_INDEX,
                           KeyConditionExpression="#e = :e",
                           ExpressionAttributeNames={"#e": schema.BY_CREATED_PK},
                           ExpressionAttributeValues={":e": {"S": schema.ENTITY}})

    def _records(self, items) -> list[AssessmentRecord]:
        return [r for r in (self._from_item(i) for i in items) if r is not None]

    # -- AssessmentStore -------------------------------------------------------------------
    def save(self, record: AssessmentRecord) -> None:
        if not _REPORT_ID.match(record.report_id):
            raise ValueError("report_id must be 32 lowercase hex characters.")
        item = self._to_item(record)
        if _item_bytes(item) > schema.MAX_ITEM_BYTES:
            raise ValueError(f"Assessment record is larger than {schema.MAX_ITEM_BYTES} bytes.")
        self.client.put_item(TableName=self.table_name, Item=item)

    def get(self, report_id: str) -> AssessmentRecord | None:
        if not _REPORT_ID.match(report_id):
            return None
        resp = self.client.get_item(TableName=self.table_name, Key={schema.ASSESSMENTS_PK: {"S": report_id}},
                                    ConsistentRead=True)
        item = resp.get("Item")
        return self._from_item(item) if item else None

    def set_checklist_item(self, report_id: str, item_id: str, completed: bool) -> AssessmentRecord | None:
        record = self.get(report_id)
        if record is None:
            return None
        updated = apply_checklist_change(record, item_id, completed)
        key = {schema.ASSESSMENTS_PK: {"S": report_id}}
        names = {"#c": schema.ATTR_CHECKLIST, "#pk": schema.ASSESSMENTS_PK}
        if updated.checklist_completed:
            expr: dict[str, Any] = {"UpdateExpression": "SET #c = :j",
                                    "ExpressionAttributeValues": {":j": {"S": self._checklist_json(updated)}}}
        else:  # back to the base attribute set
            expr = {"UpdateExpression": "REMOVE #c"}
        try:
            self.client.update_item(TableName=self.table_name, Key=key, ConditionExpression="attribute_exists(#pk)",
                                    ExpressionAttributeNames=names, **expr)
        except self.client.exceptions.ConditionalCheckFailedException:
            return None  # deleted between the read and the update
        return updated

    def all(self) -> list[AssessmentRecord]:
        return self._records(self._by_created())

    def list(self, limit: int = 20, offset: int = 0) -> list[AssessmentRecord]:
        if limit <= 0:
            return []
        return self._records(self._by_created(limit=offset + limit))[offset:offset + limit]

    def count(self) -> int:
        return sum(self._by_created(select_count=True))

    def history_for_location(self, location_key: str, limit: int = 20) -> list[AssessmentRecord]:
        if limit <= 0:
            return []
        items = self._query(limit, IndexName=schema.BY_LOCATION_INDEX, KeyConditionExpression="#k = :k",
                            ExpressionAttributeNames={"#k": schema.BY_LOCATION_PK},
                            ExpressionAttributeValues={":k": {"S": location_key}})
        return self._records(items)
