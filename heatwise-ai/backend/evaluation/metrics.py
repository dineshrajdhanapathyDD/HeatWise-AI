"""Deterministic evaluation metrics over a `PreparednessReport` and its synthetic scenario.

Per-scenario scoring functions return plain dicts; `aggregate` turns the per-scenario rows
into metric records `{value, numerator, denominator, unit, mode, status, note, details}`.
No LLM is involved in any metric here.
"""

from __future__ import annotations

import statistics
from typing import Any

from backend.agents.coordinator import AGENT_NAME, FALLBACK_AGENT, FINALIZE
from backend.evaluation.dataset import Scenario
from backend.guidance.sources import TRUSTED_SOURCES
from backend.models.plan import PlanItem
from backend.models.report import PreparednessReport

FIELD_TOLERANCE = 0.05
CURRENT_FIELDS = ("temperature_c", "apparent_temperature_c", "relative_humidity_pct", "wind_speed_kmh",
                  "precipitation_mm")
DAILY_FIELDS = ("temperature_max_c", "temperature_min_c", "apparent_temperature_max_c", "precipitation_sum_mm",
                "uv_index_max", "relative_humidity_max_pct")


def metric(value: float | None, numerator: int | None, denominator: int | None, unit: str, mode: str,
           status: str = "measured", note: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"value": value, "numerator": numerator, "denominator": denominator, "unit": unit, "mode": mode,
            "status": status, "note": note, "details": details or {}}


def ratio_metric(numerator: int, denominator: int, unit: str, mode: str, note: str = "") -> dict[str, Any]:
    value = round(numerator / denominator, 4) if denominator else None
    return metric(value, numerator, denominator, unit, mode, "measured" if denominator else "not_run", note)


def not_run(unit: str, mode: str, note: str) -> dict[str, Any]:
    return metric(None, None, None, unit, mode, "not_run", note)


# -- per-scenario scoring -----------------------------------------------------------------

def _field_ok(expected: float | None, actual: float | None, missing_fields: list[str], name: str) -> bool:
    if expected is None:
        return actual is None and name in missing_fields
    return actual is not None and abs(actual - expected) <= FIELD_TOLERANCE


def weather_extraction(report: PreparednessReport, scenario: Scenario) -> dict[str, Any]:
    """Fields in the report's current conditions and forecast days that equal the fixture."""
    w = scenario.weather
    matched = total = 0
    mismatches: list[str] = []
    fixture_current = w.current if not (w.current_error or w.geocode_error) else None
    fixture_days = w.forecast_days if not (w.forecast_error or w.geocode_error) else None

    cc = report.current_conditions
    if fixture_current is None:
        total += 1
        if cc is None:
            matched += 1
        else:
            mismatches.append("current: expected no current conditions")
    else:
        for name in CURRENT_FIELDS:
            total += 1
            exp = getattr(fixture_current, name)
            act = getattr(cc, name) if cc is not None else None
            if cc is not None and _field_ok(exp, act, cc.missing_fields, name):
                matched += 1
            else:
                mismatches.append(f"current.{name}: expected {exp}, got {act}")

    fc = report.forecast
    if fixture_days is None:
        total += 1
        if fc is None:
            matched += 1
        else:
            mismatches.append("forecast: expected no forecast")
    else:
        for i, day in enumerate(fixture_days[:scenario.forecast_days]):
            got = fc.days[i] if fc is not None and i < len(fc.days) else None
            for name in DAILY_FIELDS:
                total += 1
                exp = getattr(day, name)
                act = getattr(got, name) if got is not None else None
                if got is not None and _field_ok(exp, act, got.missing_fields, name):
                    matched += 1
                else:
                    mismatches.append(f"forecast[{i}].{name}: expected {exp}, got {act}")
    return {"matched": matched, "total": total, "mismatches": mismatches}


def renderable_items(report: PreparednessReport) -> list[PlanItem]:
    """Twin of frontend lib/safety.ts renderablePlanItems: what a user is shown."""
    plan = report.recommended_actions
    if plan is None:
        return []
    if report.status == "complete":
        return list(plan.items)
    if report.status == "needs_human_review":
        keep = set(report.verification.verified_item_ids if report.verification else [])
        return [i for i in plan.items if i.id in keep]
    return []


def source_verification(report: PreparednessReport) -> dict[str, int]:
    plan = report.recommended_actions
    items = list(plan.items) if plan is not None else []
    trusted = sum(1 for i in items if i.source_ids and all(s in TRUSTED_SOURCES for s in i.source_ids))
    verified_ids = set(report.verification.verified_item_ids) if report.verification else set()
    return {"items": len(items), "trusted_sources": trusted,
            "verified": sum(1 for i in items if i.id in verified_ids)}


def delegation(report: PreparednessReport, expected_path: list[str]) -> dict[str, Any]:
    """D-M5-5: successful coordinator / fallback delegations in step order against the expected path.

    finalize_report is not a delegation; it is compared separately (`finalized_by_model`).
    """
    entries = sorted((t for t in report.trace if t.agent in (AGENT_NAME, FALLBACK_AGENT) and t.status == "success"),
                     key=lambda t: t.step_index)
    actual = [t.tool for t in entries]
    delegations = [t for t in actual if t != FINALIZE]
    expected = [p for p in expected_path if p != FINALIZE]
    fallback_used = any(t.agent == FALLBACK_AGENT for t in entries)
    finalized_by_model = any(t.agent == AGENT_NAME and t.tool == FINALIZE for t in entries)
    effective = delegations == expected
    model_driven = effective and not fallback_used and not report.steering_blocks and finalized_by_model
    return {"actual_path": actual, "effective": effective, "model_driven": model_driven,
            "fallback_used": fallback_used, "steering_blocks": len(report.steering_blocks),
            "finalized_by_model": finalized_by_model}


def score_scenario(report: PreparednessReport, scenario: Scenario) -> dict[str, Any]:
    exp = scenario.expected
    plan = report.recommended_actions
    checks = {
        "workflow_completion": report.status == exp.status,
        "risk_agreement": report.risk_category == exp.risk_category,
        "safety_pass": report.verification_status == exp.verification_status,
    }
    if exp.requested_language is not None:
        checks["language"] = (plan is not None and plan.requested_language == exp.requested_language
                              and plan.language == exp.plan_language and bool(plan.language_notice))
    return {
        "actual": {"status": report.status, "risk_category": report.risk_category,
                   "verification_status": report.verification_status, "revision_count": report.revision_count,
                   "plan_language": plan.language if plan else None,
                   "requested_language": plan.requested_language if plan else None},
        "checks": checks,
        "weather_fields": weather_extraction(report, scenario),
        "sources": source_verification(report),
        "delegation": delegation(report, exp.path),
    }


# -- aggregation --------------------------------------------------------------------------

def failures_for(row: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sid = row["id"]
    if row.get("error"):
        return [{"scenario_id": sid, "metric": "workflow_completion", "detail": row["error"]}]
    exp, act = row["expected"], row["actual"]
    for name, ok in row["checks"].items():
        if not ok:
            key = {"workflow_completion": "status", "risk_agreement": "risk_category",
                   "safety_pass": "verification_status"}.get(name)
            detail = (f"expected {exp[key]}, got {act[key]}" if key else
                      f"plan language {act['plan_language']}, requested {act['requested_language']}")
            out.append({"scenario_id": sid, "metric": name, "detail": detail})
    for m in row["weather_fields"]["mismatches"][:3]:
        out.append({"scenario_id": sid, "metric": "weather_extraction", "detail": m})
    d = row["delegation"]
    if not d["effective"]:
        out.append({"scenario_id": sid, "metric": "delegation_order_effective",
                    "detail": f"expected {exp['path']}, got {d['actual_path']}"})
    return out


def aggregate(rows: list[dict[str, Any]], mode: str) -> dict[str, dict[str, Any]]:
    ok_rows = [r for r in rows if not r.get("error")]
    n = len(rows)

    def count(check: str) -> int:
        return sum(1 for r in ok_rows if r["checks"].get(check))

    wf_m = sum(r["weather_fields"]["matched"] for r in ok_rows)
    wf_t = sum(r["weather_fields"]["total"] for r in ok_rows)
    items = sum(r["sources"]["items"] for r in ok_rows)
    trusted = sum(r["sources"]["trusted_sources"] for r in ok_rows)
    verified = sum(r["sources"]["verified"] for r in ok_rows)
    durations = [r["duration_ms"] for r in ok_rows if r.get("duration_ms") is not None]
    lang_rows = [r for r in ok_rows if "language" in r["checks"]]

    metrics = {
        "workflow_completion": ratio_metric(count("workflow_completion"), n, "scenarios", mode,
                                            "Report produced without an exception and its status equals the "
                                            "expected status."),
        "risk_agreement": ratio_metric(count("risk_agreement"), n, "scenarios", mode,
                                       "Report risk category equals the category derived by hand from the "
                                       "documented rules (design.md 8.2). Not clinical validation."),
        "safety_pass": ratio_metric(count("safety_pass"), n, "scenarios", mode,
                                    "Report verification status (passed / failed / not_run) equals the expected "
                                    "status."),
        "weather_extraction": ratio_metric(wf_m, wf_t, "fields", mode,
                                           f"Report weather fields equal to the synthetic fixture within "
                                           f"{FIELD_TOLERANCE}; null fixture values must be null and listed as "
                                           "missing."),
        "source_verification": ratio_metric(trusted, items, "plan items", mode,
                                            "Plan items whose source ids are all in TRUSTED_SOURCES."),
        "items_verified": ratio_metric(verified, items, "plan items", mode,
                                       "Plan items that passed the deterministic safety checks."),
        "delegation_order_effective": ratio_metric(
            sum(1 for r in ok_rows if r["delegation"]["effective"]), n, "scenarios", mode,
            "Successful coordinator and deterministic-fallback delegations, in step order, equal the expected "
            "path (fallback allowed)."),
        "delegation_order_model_driven": ratio_metric(
            sum(1 for r in ok_rows if r["delegation"]["model_driven"]), n, "scenarios", mode,
            "Expected order reached by the coordinator model alone: no fallback step, no steering block, "
            "finalize_report called by the model."),
        "language_notice": ratio_metric(sum(1 for r in lang_rows if r["checks"]["language"]), len(lang_rows),
                                        "scenarios", mode,
                                        "Non-English request returns an English plan with a language notice."),
    }
    if durations:
        metrics["timing_ms"] = metric(round(statistics.mean(durations), 1), None, len(durations), "ms per scenario",
                                      mode, note="Wall-clock time of one coordinator run (perf_counter).",
                                      details={"mean": round(statistics.mean(durations), 1),
                                               "median": round(statistics.median(durations), 1),
                                               "max": round(max(durations), 1)})
    else:
        metrics["timing_ms"] = not_run("ms per scenario", mode, "No scenario finished.")
    return metrics
