"""Local assessment store (Milestone 3).

`JsonFileAssessmentStore` keeps one `<report_id>.json` per record, written atomically
(temp file + `os.replace`). A record holds only the request (place, forecast days,
community profile), the report and community-level checklist progress (item id ->
completed at); no personal data. M4 can swap in another `AssessmentStore` implementation.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from backend.api.schemas import AssessmentRequest
from backend.models.report import PreparednessReport

logger = logging.getLogger("heatwise.store")

_REPORT_ID = re.compile(r"^[0-9a-f]{32}$")


class AssessmentRecord(BaseModel):
    report_id: str
    created_at: datetime
    duration_ms: float | None = None
    request: AssessmentRequest
    report: PreparednessReport
    # Checklist item id -> completed at (D-M5-9). Omitted from JSON while empty, so records
    # without progress keep their M3/M4 shape and old records parse.
    checklist_completed: dict[str, datetime] = Field(default_factory=dict, exclude_if=lambda v: not v)


def apply_checklist_change(record: AssessmentRecord, item_id: str, completed: bool) -> AssessmentRecord:
    """Copy of `record` with `item_id` marked done (keeps the first completion time) or not done."""
    progress = dict(record.checklist_completed)
    if completed:
        progress.setdefault(item_id, datetime.now(timezone.utc))
    else:
        progress.pop(item_id, None)
    return record.model_copy(update={"checklist_completed": progress})


class AssessmentStore(ABC):
    @abstractmethod
    def save(self, record: AssessmentRecord) -> None: ...

    @abstractmethod
    def get(self, report_id: str) -> AssessmentRecord | None: ...

    @abstractmethod
    def all(self) -> list[AssessmentRecord]:
        """Every readable record, newest first."""

    def list(self, limit: int = 20, offset: int = 0) -> list[AssessmentRecord]:
        return self.all()[offset:offset + limit]

    def count(self) -> int:
        return len(self.all())

    def history_for_location(self, location_key: str, limit: int = 20) -> list[AssessmentRecord]:
        """Newest-first records whose report has this `summaries.location_key`."""
        from backend.api.summaries import location_key as key_of  # avoids an import cycle

        return [r for r in self.all() if key_of(r.report) == location_key][:max(limit, 0)]

    def set_checklist_item(self, report_id: str, item_id: str, completed: bool) -> AssessmentRecord | None:
        """Mark one checklist item done or not done; None when the report does not exist.
        The caller checks that `item_id` is renderable. Default: get, change, save."""
        record = self.get(report_id)
        if record is None:
            return None
        updated = apply_checklist_change(record, item_id, completed)
        self.save(updated)
        return updated


class JsonFileAssessmentStore(AssessmentStore):
    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self._lock = threading.Lock()

    def _path(self, report_id: str) -> Path | None:
        if not _REPORT_ID.match(report_id):
            return None  # also keeps arbitrary ids from reaching the filesystem
        return self.directory / f"{report_id}.json"

    def _write(self, path: Path, record: AssessmentRecord) -> None:
        """Atomic write; the caller holds the lock."""
        data = record.model_dump_json(indent=2)
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def _read(path: Path) -> AssessmentRecord | None:
        """The caller holds the lock."""
        if not path.is_file():
            return None
        try:
            return AssessmentRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("unreadable assessment record skipped: %s", path.name)
            return None

    def save(self, record: AssessmentRecord) -> None:
        path = self._path(record.report_id)
        if path is None:
            raise ValueError("report_id must be 32 lowercase hex characters.")
        with self._lock:
            self._write(path, record)

    def get(self, report_id: str) -> AssessmentRecord | None:
        path = self._path(report_id)
        if path is None:
            return None
        with self._lock:
            return self._read(path)

    def set_checklist_item(self, report_id: str, item_id: str, completed: bool) -> AssessmentRecord | None:
        path = self._path(report_id)
        if path is None:
            return None
        with self._lock:  # read-modify-write under one lock
            record = self._read(path)
            if record is None:
                return None
            updated = apply_checklist_change(record, item_id, completed)
            self._write(path, updated)
            return updated

    def all(self) -> list[AssessmentRecord]:
        out: list[AssessmentRecord] = []
        with self._lock:
            if not self.directory.is_dir():
                return []
            for path in self.directory.glob("*.json"):
                if path.name.startswith(".tmp-"):
                    continue
                try:
                    out.append(AssessmentRecord.model_validate_json(path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    logger.warning("unreadable assessment record skipped: %s", path.name)
        out.sort(key=lambda r: r.created_at, reverse=True)
        return out
