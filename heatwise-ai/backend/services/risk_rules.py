"""Deterministic community heat-risk rules.

Every threshold below carries the URL of the page it was verified on; each URL is
an entry in `backend.guidance.sources.TRUSTED_SOURCES`.

1. Current heat index (NWS/WPC Rothfusz algorithm) from air temperature and
   relative humidity, banded per the NWS classification table -> score 0-4.
2. Forecast daily maximum air temperature against the IMD actual-maximum
   criteria published by WHO India -> score 0-4. This is an indication for a
   forecast grid point, never an official heat-wave declaration.
3. Hazard = max(1, 2). Category: 0 low, 1 moderate, 2 high, 3 very_high, 4 extreme.
4. Vulnerability adjustment: a configurable PROJECT HEURISTIC (not an official
   standard). If hazard >= 1 and the number of community vulnerability
   indicators >= `min_indicators`, raise one category step (capped at extreme).

Open-Meteo's apparent temperature is a different metric from the NWS heat index,
so it is reported as evidence only and never fed into the bands.
"""

from __future__ import annotations

import math

from backend.models.risk import CommunityProfile, RiskAssessment, RiskFactor
from backend.models.weather import WeatherIntelligenceResult

RULES_VERSION = "m2-risk-rules-1"

NWS_HEAT_INDEX_URL = "https://www.weather.gov/ama/heatindex"
WPC_EQUATION_URL = "https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml"
WHO_INDIA_URL = "https://www.who.int/india/heat-waves"
WHO_FACTSHEET_URL = "https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health"

CATEGORIES = ("low", "moderate", "high", "very_high", "extreme")

# NWS heat index classification (°F lower bounds). Source: https://www.weather.gov/ama/heatindex
HI_CAUTION_F = 80.0          # Caution 80-90°F            https://www.weather.gov/ama/heatindex
HI_EXTREME_CAUTION_F = 90.0  # Extreme Caution 90-103°F   https://www.weather.gov/ama/heatindex
HI_DANGER_F = 103.0          # Danger 103-124°F           https://www.weather.gov/ama/heatindex
HI_EXTREME_DANGER_F = 125.0  # Extreme Danger >= 125°F    https://www.weather.gov/ama/heatindex
NWS_BANDS = (  # (lower bound °F, band name, hazard score)
    (HI_EXTREME_DANGER_F, "Extreme Danger", 4),
    (HI_DANGER_F, "Danger", 3),
    (HI_EXTREME_CAUTION_F, "Extreme Caution", 2),
    (HI_CAUTION_F, "Caution", 1),
)

# IMD actual-maximum criteria as published by WHO India. Source: https://www.who.int/india/heat-waves
IMD_PLAINS_CONSIDER_C = 40.0     # heat wave considered only if max >= 40°C (plains)  https://www.who.int/india/heat-waves
IMD_HEAT_WAVE_C = 45.0           # heat wave: actual max >= 45°C                      https://www.who.int/india/heat-waves
IMD_SEVERE_HEAT_WAVE_C = 47.0    # severe heat wave: actual max >= 47°C               https://www.who.int/india/heat-waves
IMD_SCORES = {"none": 0, "threshold_met": 1, "heat_wave": 3, "severe_heat_wave": 4}


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def heat_index_f(t_f: float, rh: float) -> float:
    """NWS heat index in °F. Algorithm: https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml"""
    # Simple (Steadman-consistent) formula first, averaged with the temperature.
    simple = 0.5 * (t_f + 61.0 + (t_f - 68.0) * 1.2 + rh * 0.094)
    hi = (simple + t_f) / 2.0
    if hi < 80.0:  # regression applies only at >= 80°F  https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
        return hi
    t, r = t_f, rh
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * r - 0.22475541 * t * r - 0.00683783 * t * t
          - 0.05481717 * r * r + 0.00122874 * t * t * r + 0.00085282 * t * r * r - 0.00000199 * t * t * r * r)
    # Low-humidity adjustment: RH < 13% and 80-112°F  https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    if r < 13.0 and 80.0 <= t <= 112.0:
        hi -= ((13.0 - r) / 4.0) * math.sqrt((17.0 - abs(t - 95.0)) / 17.0)
    # High-humidity adjustment: RH > 85% and 80-87°F  https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    elif r > 85.0 and 80.0 <= t <= 87.0:
        hi += ((r - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return hi


def nws_band(hi_f: float) -> tuple[str | None, int]:
    """Return (band name or None below Caution, hazard score 0-4). https://www.weather.gov/ama/heatindex"""
    for lower, name, score in NWS_BANDS:
        if hi_f >= lower:
            return name, score
    return None, 0


def imd_indication(max_c: float | None, terrain: str | None) -> str | None:
    """IMD actual-maximum indication for plains (or unknown terrain, assumed plains).

    Returns None when the rule is not applied (no value, or hilly/coastal terrain, whose
    criteria need departure-from-normal data we do not have).
    Source: https://www.who.int/india/heat-waves
    """
    if max_c is None or terrain in ("hilly", "coastal"):
        return None
    if max_c >= IMD_SEVERE_HEAT_WAVE_C:
        return "severe_heat_wave"
    if max_c >= IMD_HEAT_WAVE_C:
        return "heat_wave"
    if max_c >= IMD_PLAINS_CONSIDER_C:
        return "threshold_met"
    return "none"


def _r1(x: float) -> float:
    return round(x, 1)


def classify(
    weather: WeatherIntelligenceResult | None,
    profile: CommunityProfile | None,
    min_indicators: int = 2,
) -> RiskAssessment:
    profile = profile or CommunityProfile()
    indicators = profile.indicators()
    missing: list[str] = []
    factors: list[RiskFactor] = []
    source_ids: list[str] = []

    current = weather.current if weather is not None else None
    forecast = weather.forecast if weather is not None else None
    temp_c = current.temperature_c if current is not None else None
    rh = current.relative_humidity_pct if current is not None else None
    has_current = temp_c is not None and rh is not None
    highs = [d.temperature_max_c for d in forecast.days if d.temperature_max_c is not None] if forecast else []
    fc_max = max(highs) if highs else None
    has_forecast = fc_max is not None

    if not has_current:
        missing.append("Current temperature and relative humidity unavailable; heat index not computed.")
    if not has_forecast:
        missing.append("Forecast maximum temperature unavailable; IMD actual-maximum indication not computed.")

    if not has_current and not has_forecast:
        return RiskAssessment(
            status="insufficient_data", category="unknown", confidence="low",
            vulnerability_indicators=indicators, missing_data=missing, rules_version=RULES_VERSION,
        )

    hi_f = hi_c = None
    band = None
    hi_score = 0
    if has_current:
        hi_f = heat_index_f(c_to_f(temp_c), rh)  # type: ignore[arg-type]
        hi_c = f_to_c(hi_f)
        band, hi_score = nws_band(hi_f)
        factors.append(RiskFactor(
            code="heat_index",
            description=f"Current NWS heat index from {temp_c:g}°C and {rh:g}% relative humidity"
                        f" (band: {band or 'below Caution'}).",
            value=_r1(hi_c), unit="°C", source_id="nws_heat_index"))
        source_ids += ["nws_heat_index", "wpc_heat_index_equation"]
    if current is not None and current.apparent_temperature_c is not None:
        factors.append(RiskFactor(
            code="apparent_temperature",
            description="Provider apparent temperature, shown as evidence only (a different metric from the "
                        "NWS heat index; not used in the bands).",
            value=current.apparent_temperature_c, unit="°C", source_id=None))

    indication = imd_indication(fc_max, profile.terrain)
    imd_score = IMD_SCORES[indication] if indication is not None else 0
    if has_forecast:
        if indication is not None:
            factors.append(RiskFactor(
                code="forecast_max_temperature",
                description=f"Highest forecast daily maximum compared with IMD actual-maximum criteria "
                            f"(indication: {indication}). Not an official declaration.",
                value=fc_max, unit="°C", source_id="who_india_heat_waves"))
            source_ids.append("who_india_heat_waves")
            missing.append("Departure-from-normal criteria not evaluated: climatological normals unavailable.")
            missing.append("IMD declares a heat wave only when criteria are met at two or more stations for two "
                           "consecutive days; this is a single forecast point.")
        else:
            factors.append(RiskFactor(
                code="forecast_max_temperature",
                description="Highest forecast daily maximum (IMD actual-maximum rule not applied for "
                            f"{profile.terrain} terrain).",
                value=fc_max, unit="°C", source_id=None))
            missing.append(f"IMD actual-maximum criteria not applied for {profile.terrain} terrain; its criteria "
                           "need departure-from-normal data that is unavailable.")
    if profile.terrain is None:
        missing.append("Terrain not provided; plains assumed for the IMD actual-maximum indication.")
    if weather is not None and weather.is_stale:
        missing.append("Current conditions are older than the freshness threshold.")
    if weather is not None and weather.data_mode == "demo":
        missing.append("Demonstration data, not real weather.")

    hazard = max(hi_score, imd_score)
    score = hazard
    adjusted = False
    # PROJECT HEURISTIC (configurable via RISK_VULNERABILITY_MIN_INDICATORS), not an official standard.
    # Rationale only: https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health
    if hazard >= 1 and len(indicators) >= min_indicators:
        score = min(hazard + 1, 4)
        adjusted = score != hazard
        factors.append(RiskFactor(
            code="vulnerability_heuristic",
            description=f"Project heuristic (not an official standard): {len(indicators)} community vulnerability "
                        f"indicator(s) present (threshold {min_indicators}); category raised one step.",
            value=float(len(indicators)), unit="indicators", source_id="who_heat_health_factsheet"))
        source_ids.append("who_heat_health_factsheet")

    if not (has_current and has_forecast):
        confidence = "low"
    elif (weather is not None and weather.is_stale) or profile.terrain is None:
        confidence = "medium"
    else:
        confidence = "high"

    return RiskAssessment(
        status="ok",
        category=CATEGORIES[score],  # type: ignore[arg-type]
        hazard_score=hazard,
        heat_index_c=_r1(hi_c) if hi_c is not None else None,
        heat_index_f=_r1(hi_f) if hi_f is not None else None,
        heat_index_band=band,
        imd_indication=indication,  # type: ignore[arg-type]
        contributing_factors=factors,
        vulnerability_indicators=indicators,
        heuristic_adjustment_applied=adjusted,
        confidence=confidence,  # type: ignore[arg-type]
        missing_data=missing,
        rules_version=RULES_VERSION,
        source_ids=list(dict.fromkeys(source_ids)),
    )


def rules_table() -> dict:
    """The rule tables, for the get_risk_rules tool and documentation."""
    return {
        "rules_version": RULES_VERSION,
        "heat_index_bands_f": [
            {"band": "Caution", "from_f": HI_CAUTION_F, "to_f": HI_EXTREME_CAUTION_F, "score": 1},
            {"band": "Extreme Caution", "from_f": HI_EXTREME_CAUTION_F, "to_f": HI_DANGER_F, "score": 2},
            {"band": "Danger", "from_f": HI_DANGER_F, "to_f": HI_EXTREME_DANGER_F, "score": 3},
            {"band": "Extreme Danger", "from_f": HI_EXTREME_DANGER_F, "to_f": None, "score": 4},
        ],
        "heat_index_sources": [NWS_HEAT_INDEX_URL, WPC_EQUATION_URL],
        "imd_actual_max_c": [
            {"indication": "threshold_met", "from_c": IMD_PLAINS_CONSIDER_C, "score": 1},
            {"indication": "heat_wave", "from_c": IMD_HEAT_WAVE_C, "score": 3},
            {"indication": "severe_heat_wave", "from_c": IMD_SEVERE_HEAT_WAVE_C, "score": 4},
        ],
        "imd_note": "Applied to the forecast maximum for plains or unknown terrain only. An indication, "
                    "not an official heat wave declaration.",
        "imd_source": WHO_INDIA_URL,
        "categories": {str(i): c for i, c in enumerate(CATEGORIES)},
        "vulnerability_heuristic": "Project heuristic, not an official standard: if hazard >= 1 and the "
                                   "number of community vulnerability indicators reaches the configured "
                                   "threshold, raise one category step (capped at extreme).",
        "vulnerability_rationale_source": WHO_FACTSHEET_URL,
    }
