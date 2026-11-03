"""DynamoDB table layout shared by the stores and the CDK app (Milestone 4, D-M4-6).

Constants only; no boto3 import, so `infrastructure/` can import this module cheaply.

Assessments table: partition key `report_id`. GSI `by_location` (location_key, created_at)
serves per-place history; GSI `by_created` (entity, created_at) lists every record newest
first. Jobs table: partition key `job_id`, sparse GSI `pending` (pending_pk, created_at),
TTL on `expires_at`.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Assessments table
ASSESSMENTS_PK = "report_id"
BY_LOCATION_INDEX = "by_location"
BY_LOCATION_PK = "location_key"
BY_CREATED_INDEX = "by_created"
BY_CREATED_PK = "entity"
CREATED_AT = "created_at"  # sort key of both assessment indexes and of the pending jobs index
ENTITY = "assessment"
ATTR_REQUEST = "request_json"
ATTR_REPORT = "report_json"
ATTR_DURATION = "duration_ms"
# Optional checklist progress (D-M5-9): JSON {item_id: ts}, present only when non-empty.
ATTR_CHECKLIST = "checklist_json"

# Jobs table
JOBS_PK = "job_id"
PENDING_INDEX = "pending"
PENDING_PK = "pending_pk"
PENDING_VALUE = "pending"
TTL_ATTR = "expires_at"

# DynamoDB items are limited to 400 KB; keep a margin for attribute names and overhead.
MAX_ITEM_BYTES = 380_000

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def ts(dt: datetime | None = None) -> str:
    """UTC timestamp that sorts lexicographically, e.g. 2026-05-10T09:00:00.000000Z."""
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(_TS_FORMAT)


def parse_ts(value: str) -> datetime:
    """Inverse of `ts`: an aware UTC datetime."""
    return datetime.strptime(value, _TS_FORMAT).replace(tzinfo=timezone.utc)
