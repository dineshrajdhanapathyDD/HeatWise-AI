"""Single list of trusted sources used by HeatWise AI rules and guidance.

Only pages that were actually fetched and read are listed here. `verified_on` is
the date the page was fetched; `verified_content` summarises (in our own words)
what was confirmed on the page and what HeatWise uses it for. PDFs that could
not be read are deliberately not listed.
"""

from __future__ import annotations

from pydantic import BaseModel


class TrustedSource(BaseModel):
    id: str
    title: str
    publisher: str
    url: str
    verified_on: str  # ISO date the page was fetched and read
    verified_content: str


_SOURCES = [
    TrustedSource(
        id="nws_heat_index",
        title="What is the heat index?",
        publisher="US National Weather Service (NWS Amarillo)",
        url="https://www.weather.gov/ama/heatindex",
        verified_on="2026-11-02",
        verified_content=(
            "Heat index classification table: Caution 80-90°F, Extreme Caution 90-103°F, Danger 103-124°F, "
            "Extreme Danger 125°F or higher. Chart examples: 100°F at 55% RH gives 124°F; 100°F at 15% RH "
            "gives 96°F. The regression equation has an error of about ±1.3°F. Chart values are for shade; "
            "direct sun can add up to 15°F."
        ),
    ),
    TrustedSource(
        id="wpc_heat_index_equation",
        title="The Heat Index Equation",
        publisher="NOAA Weather Prediction Center",
        url="https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml",
        verified_on="2026-11-02",
        verified_content=(
            "Rothfusz regression coefficients; low-humidity adjustment (RH < 13% and 80-112°F, subtracted) and "
            "high-humidity adjustment (RH > 85% and 80-87°F, added); the simple Steadman-consistent formula is "
            "computed first and averaged with temperature, and the full regression is used only when that "
            "result is 80°F or higher."
        ),
    ),
    TrustedSource(
        id="who_india_heat_waves",
        title="Heat waves (WHO India)",
        publisher="World Health Organization, Country Office for India",
        url="https://www.who.int/india/heat-waves",
        verified_on="2026-11-02",
        verified_content=(
            "IMD criteria as published by WHO India: a heat wave is considered only if a station's maximum "
            "temperature reaches at least 40°C (plains) or 30°C (hilly regions). By actual maximum temperature: "
            "heat wave when >= 45°C, severe heat wave when >= 47°C. Departure-from-normal criteria also exist "
            "(4.5-6.4°C above normal; severe above 6.4°C). Declared when met at >= 2 stations in a "
            "meteorological sub-division for >= 2 consecutive days. Coastal stations use a departure-based "
            "criterion with actual maximum of at least 37°C."
        ),
    ),
    TrustedSource(
        id="who_heat_health_factsheet",
        title="Climate change, heat and health (fact sheet)",
        publisher="World Health Organization",
        url="https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health",
        verified_on="2026-11-02",
        verified_content=(
            "Vulnerability to heat is shaped by physiological factors (age, health status) and exposure factors "
            "(occupation, socio-economic conditions, housing, access to cooling); outdoor and manual workers are "
            "exposed through their work. Public actions: stay out of the heat at the hottest time of day, seek "
            "shade, keep homes cool, drink water regularly, check on vulnerable people, protect infants and "
            "children. Used as rationale for the vulnerability heuristic, not for its numbers."
        ),
    ),
    # Guidance sources for the Preparedness Action Planner catalog (backend/guidance/catalog.py).
    # Tried but not readable on 2026-11-02 (not cited): osha.gov heat pages and cdc.gov/niosh (HTTP 403),
    # 112.gov.in and 112.gov.in/faq (timeout), ndma.gov.in heat-wave pages (404 / PDF only). Because no
    # emergency number could be verified for India, escalation text names no number.
    TrustedSource(
        id="ready_gov_extreme_heat",
        title="Extreme Heat",
        publisher="Ready.gov (US Department of Homeland Security / FEMA)",
        url="https://www.ready.gov/heat",
        verified_on="2026-11-02",
        verified_content=(
            "Household actions before and during extreme heat: learn the signs of heat illness, do not rely on a "
            "fan as the main cooling device, find cool places in the community, cover windows, never leave people "
            "or pets in a closed car, take cool showers, wear loose light clothing, find shade and wear a wide hat "
            "outside, drink plenty of fluids, avoid high-energy activity or outdoor work in midday heat, check on "
            "family, older adults and neighbours. Heat stroke signs (very high body temperature, hot dry skin, "
            "fast pulse, confusion) need emergency help or a hospital immediately, while moving the person to a "
            "cool shaded place and cooling them with wet cloths. For heat cramps or exhaustion: move somewhere "
            "cooler, remove extra clothing, sip water; contact a health provider if symptoms worsen or last more "
            "than an hour. The page's emergency number is for the US and is not used by HeatWise."
        ),
    ),
    TrustedSource(
        id="nws_heat_safety",
        title="Heat Safety Tips and Resources",
        publisher="US National Weather Service",
        url="https://www.weather.gov/safety/heat",
        verified_on="2026-11-02",
        verified_content=(
            "Groups particularly vulnerable to heat: infants and young children, older adults, people with chronic "
            "medical conditions and pregnant women; check in on friends and relatives in these groups. It is never "
            "safe to leave a child, disabled person or pet locked in a car."
        ),
    ),
    TrustedSource(
        id="who_workplace_heat_stress",
        title="Workplace heat stress (questions and answers)",
        publisher="World Health Organization",
        url="https://www.who.int/news-room/questions-and-answers/item/workplace-heat-stress",
        verified_on="2026-11-02",
        verified_content=(
            "Workplace heat stress comes from metabolic heat, the environment and clothing. Heat exhaustion and "
            "heat stroke are severe outcomes that require an emergency response. Older and middle-aged workers, "
            "people with chronic health conditions, pregnant women, outdoor workers and those doing intense "
            "physical work are more vulnerable. WHO recommends heat action programmes and training workers and "
            "employers to recognise heat stress symptoms."
        ),
    ),
    TrustedSource(
        id="fao_extreme_heat_agrifood",
        title="Extreme heat in an El Niño year: how agrifood systems can prepare",
        publisher="Food and Agriculture Organization of the United Nations",
        url="https://www.fao.org/climate-change/news/news-detail/extreme-heat-in-an-el-ni%C3%B1o-year--how-agrifood-systems-can-prepare/en",
        verified_on="2026-11-02",
        verified_content=(
            "Extreme heat harms crops, livestock and agricultural workers. Practical measures: use early warnings "
            "and local advisories; keep soil moist with mulch; shade vegetables, store extra water, irrigate in "
            "cooler hours and keep produce out of the sun; feed cattle in cooler hours; prioritise shade for "
            "poultry, which cannot sweat. Protect farm workers by planning work around forecasts, providing shade, "
            "water and rest breaks, and training people to recognise early signs of heat stress."
        ),
    ),
    TrustedSource(
        id="wsu_livestock_heat_wave",
        title="Protect livestock, pets during summer heat wave",
        publisher="Washington State University Extension (WSU Insider)",
        url="https://news.wsu.edu/news/2022/07/28/protect-livestock-pets-during-summer-heat-wave/",
        verified_on="2026-11-02",
        verified_content=(
            "Give animals a continuous supply of cool, clean water and watch for dehydration (lethargy, dry or "
            "sunken eyes); keep water clean because warm stagnant water can grow toxic blue-green algae; handle "
            "livestock only in the early morning or evening; ventilate barns and sheds; shade animals kept outside; "
            "during and after heat stress, watch for respiratory and digestive problems; contact extension "
            "specialists or a local veterinarian for help."
        ),
    ),
]

TRUSTED_SOURCES: dict[str, TrustedSource] = {s.id: s for s in _SOURCES}


def source_url(source_id: str) -> str:
    return TRUSTED_SOURCES[source_id].url
