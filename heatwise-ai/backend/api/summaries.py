"""History summaries and metrics computed from stored assessment records (D-M3-6).

Everything here is counted or read from stored reports; nothing is estimated.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean

from backend.api.checklist import renderable_item_ids
from backend.api.schemas import (ChecklistCounts, HistoryChanges, HistoryItem, LocalizedGuidanceCounts,
                                 MetricsView, VerificationCounts)
from backend.models.report import PreparednessReport
from backend.session.store import AssessmentRecord

STATUSES = ("complete", "needs_human_review", "incomplete")
RISK_CATEGORIES = ("low", "moderate", "high", "very_high", "extreme", "unknown")
DATA_MODES = ("live", "demo")


def location_key(report: PreparednessReport) -> str:
    """Resolved `name|admin1|country` lowercased, else the query."""
    loc = report.location
    if loc is not None:
        return "|".join(p or "" for p in (loc.name, loc.admin1, loc.country)).lower()
    return report.query.strip().lower()


def max_forecast_c(report: PreparednessReport) -> float | None:
    if report.forecast is not None:
        values = [d.temperature_max_c for d in report.forecast.days if d.temperature_max_c is not None]
    else:  # reports stored before the forecast field existed
        values = [e.value for e in report.evidence
                  if e.kind == "forecast_max_temperature" and isinstance(e.value, (int, float))]
    return max(values) if values else None


def _indicators(record: AssessmentRecord) -> list[str]:
    return record.request.profile_as_community().indicators()


def _delta(new: float | None, old: float | None) -> float | None:
    return round(new - old, 1) if new is not None and old is not None else None


def _item(record: AssessmentRecord) -> HistoryItem:
    r = record.report
    return HistoryItem(
        report_id=record.report_id, created_at=record.created_at, duration_ms=record.duration_ms,
        query=r.query, location_name=r.location.name if r.location else None,
        admin1=r.location.admin1 if r.location else None, country=r.location.country if r.location else None,
        status=r.status, risk_category=r.risk_category, heat_index_c=r.risk.heat_index_c if r.risk else None,
        max_forecast_c=max_forecast_c(r), indicators=_indicators(record), data_mode=r.weather_source.data_mode,
        verification_status=r.verification_status,
    )


def history_items(records_newest_first: Sequence[AssessmentRecord]) -> list[HistoryItem]:
    """One item per record; `changes` compares with the next older record of the same location key."""
    items = [_item(rec) for rec in records_newest_first]
    keys = [location_key(rec.report) for rec in records_newest_first]
    for i, item in enumerate(items):
        prev = next((j for j in range(i + 1, len(items)) if keys[j] == keys[i]), None)
        if prev is None:
            continue
        old = items[prev]
        item.changes = HistoryChanges(
            previous_report_id=old.report_id, previous_created_at=old.created_at,
            risk_category_from=old.risk_category, risk_category_to=item.risk_category,
            heat_index_delta_c=_delta(item.heat_index_c, old.heat_index_c),
            max_forecast_delta_c=_delta(item.max_forecast_c, old.max_forecast_c),
            indicators_added=[x for x in item.indicators if x not in old.indicators],
            indicators_removed=[x for x in old.indicators if x not in item.indicators],
        )
    return items


def compute_metrics(records: Sequence[AssessmentRecord]) -> MetricsView:
    by_status = dict.fromkeys(STATUSES, 0)
    by_risk = dict.fromkeys(RISK_CATEGORIES, 0)
    by_mode = dict.fromkeys(DATA_MODES, 0)
    verification = VerificationCounts()
    pcts: list[float] = []
    durations: list[float] = []
    plans = 0
    plan_items = verified_items = 0
    checklist = ChecklistCounts()
    languages = LocalizedGuidanceCounts()
    for rec in records:
        r = rec.report
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_risk[r.risk_category] = by_risk.get(r.risk_category, 0) + 1
        mode = r.weather_source.data_mode or "unknown"
        by_mode[mode] = by_mode.get(mode, 0) + 1
        setattr(verification, r.verification_status, getattr(verification, r.verification_status) + 1)
        plan = r.recommended_actions
        if plan is not None:
            plans += 1
            verified = set(r.verification.verified_item_ids) if r.verification is not None else set()
            plan_items += len(plan.items)
            verified_items += sum(1 for i in plan.items if i.id in verified)
            if plan.language == plan.requested_language:
                languages.served_in_requested_language += 1
            else:
                languages.english_fallback += 1
            by_lang = languages.by_requested_language
            by_lang[plan.requested_language] = by_lang.get(plan.requested_language, 0) + 1
        renderable = renderable_item_ids(r)
        done = sum(1 for i in renderable if i in rec.checklist_completed)
        checklist.items_available += len(renderable)
        checklist.items_completed += done
        checklist.reports_with_progress += 1 if done else 0
        if r.verification is not None:
            pcts.append(r.verification.pct_items_verified)
        if rec.duration_ms is not None:
            durations.append(rec.duration_ms)
    return MetricsView(
        total=len(records), by_status=by_status, by_risk_category=by_risk, by_data_mode=by_mode,
        plans_generated=plans, verification=verification,
        mean_pct_items_verified=round(fmean(pcts), 1) if pcts else None,
        mean_duration_ms=round(fmean(durations), 1) if durations else None,
        assessments_completed=by_status["complete"],
        pct_recommendations_verified=round(100 * verified_items / plan_items, 1) if plan_items else None,
        checklist=checklist, localized_guidance=languages,
    )
