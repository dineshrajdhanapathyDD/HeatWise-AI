"""Verified guidance catalog for the Preparedness Action Planner.

Every item is a short paraphrase (our own words, no long quotes) of advice found on
a page listed in `backend.guidance.sources.TRUSTED_SOURCES`. The planner model may
only select items by id; it cannot change their text. Escalation items name no
emergency number because none could be verified for India (see sources.py).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Audience = Literal["household", "outdoor_worker", "farmer"]
Phase = Literal["before", "during", "after"]
Topic = Literal["hydration", "rest", "shade", "cooling", "escalation", "check_others", "work_schedule",
                "livestock_crops", "stay_informed"]

AUDIENCES: tuple[str, ...] = ("household", "outdoor_worker", "farmer")
PHASES: tuple[str, ...] = ("before", "during", "after")
REQUIRED_TOPICS: tuple[str, ...] = ("hydration", "rest", "shade", "escalation")
# Risk categories in increasing order; an item applies when the risk is at or above its min_category.
CATEGORY_ORDER: tuple[str, ...] = ("low", "moderate", "high", "very_high", "extreme")

ESCALATION_CONTACT = "contact local emergency services or the nearest health facility"


class GuidanceItem(BaseModel):
    id: str
    audience: Audience
    phase: Phase
    topic: Topic
    text: str
    source_ids: list[str] = Field(min_length=1)
    min_category: str = "low"


def _g(id: str, audience: str, phase: str, topic: str, text: str, *sources: str,
       min_category: str = "low") -> GuidanceItem:
    return GuidanceItem(id=id, audience=audience, phase=phase, topic=topic, text=text,  # type: ignore[arg-type]
                        source_ids=list(sources), min_category=min_category)


_ITEMS = [
    # ---- household -------------------------------------------------------------------------
    _g("hh-before-cooling-1", "household", "before", "cooling",
       "Keep the home cooler by covering windows with curtains or shades, and find nearby cool public places "
       "you can go to during the hottest days.", "ready_gov_extreme_heat"),
    _g("hh-before-hydration-1", "household", "before", "hydration",
       "Keep drinking water within easy reach of everyone at home so people can drink regularly on hot days.",
       "who_heat_health_factsheet"),
    _g("hh-before-check_others-1", "household", "before", "check_others",
       "Note the older people, young children, pregnant women and people with chronic illness nearby whom you "
       "will check on during hot days.", "nws_heat_safety", "who_heat_health_factsheet"),
    _g("hh-before-escalation-1", "household", "before", "escalation",
       "Learn the signs of heat illness, such as heavy sweating, dizziness, confusion, fainting or hot dry skin, "
       f"and know how to {ESCALATION_CONTACT}.", "ready_gov_extreme_heat"),
    _g("hh-before-stay_informed-1", "household", "before", "stay_informed",
       "Follow weather forecasts and any official heat warnings issued by local authorities.",
       "who_heat_health_factsheet"),
    _g("hh-during-hydration-1", "household", "during", "hydration",
       "Drink water regularly through the day.", "who_heat_health_factsheet", "ready_gov_extreme_heat"),
    _g("hh-during-rest-1", "household", "during", "rest",
       "Avoid heavy activity during the hottest part of the day and rest in the coolest place available.",
       "ready_gov_extreme_heat", "who_heat_health_factsheet"),
    _g("hh-during-shade-1", "household", "during", "shade",
       "If you need to go outside, stay in the shade and wear a wide hat and loose, light-coloured clothing.",
       "ready_gov_extreme_heat", "who_heat_health_factsheet"),
    _g("hh-during-cooling-1", "household", "during", "cooling",
       "Take cool showers or baths and cook less with the oven; do not rely on a fan as your main way to "
       "cool down.", "ready_gov_extreme_heat"),
    _g("hh-during-check_others-1", "household", "during", "check_others",
       "Check regularly on older family members, neighbours and young children, and never leave children or "
       "pets in a parked vehicle.", "ready_gov_extreme_heat", "nws_heat_safety", "who_heat_health_factsheet"),
    _g("hh-during-escalation-1", "household", "during", "escalation",
       f"If someone is confused, faints or has very hot, dry skin, {ESCALATION_CONTACT} immediately, move them "
       "to a cool shaded place and cool them with wet cloths.", "ready_gov_extreme_heat"),
    _g("hh-after-hydration-1", "household", "after", "hydration",
       "Keep drinking water regularly while it stays hot, and refill stored drinking water for the next hot "
       "spell.", "who_heat_health_factsheet"),
    _g("hh-after-rest-1", "household", "after", "rest",
       "Rest and recover in a cool place; if cramps or tiredness from the heat appear, move somewhere cooler, "
       "remove extra clothing and sip water.", "ready_gov_extreme_heat"),
    _g("hh-after-escalation-1", "household", "after", "escalation",
       "If heat cramps or exhaustion get worse or last more than an hour, contact a health provider or the "
       "nearest health facility.", "ready_gov_extreme_heat"),
    _g("hh-after-check_others-1", "household", "after", "check_others",
       "Keep checking on vulnerable neighbours and relatives until the heat has passed.",
       "nws_heat_safety", "who_heat_health_factsheet"),
    # ---- outdoor workers -------------------------------------------------------------------
    _g("ow-before-work_schedule-1", "outdoor_worker", "before", "work_schedule",
       "Plan heavy outdoor work around the forecast, moving it away from the midday heat where possible.",
       "fao_extreme_heat_agrifood", "ready_gov_extreme_heat"),
    _g("ow-before-shade-1", "outdoor_worker", "before", "shade",
       "Arrange shaded rest areas close to the work site before hot days.", "fao_extreme_heat_agrifood"),
    _g("ow-before-hydration-1", "outdoor_worker", "before", "hydration",
       "Make sure enough drinking water is available at the work site.", "fao_extreme_heat_agrifood"),
    _g("ow-before-escalation-1", "outdoor_worker", "before", "escalation",
       "Learn the early signs of heat stress and agree in advance how the team will "
       f"{ESCALATION_CONTACT} from the work site.", "fao_extreme_heat_agrifood", "who_workplace_heat_stress"),
    _g("ow-during-hydration-1", "outdoor_worker", "during", "hydration",
       "Drink water regularly throughout the work shift.", "fao_extreme_heat_agrifood",
       "who_heat_health_factsheet"),
    _g("ow-during-rest-1", "outdoor_worker", "during", "rest",
       "Take regular rest breaks in the shade or another cool place.", "fao_extreme_heat_agrifood"),
    _g("ow-during-shade-1", "outdoor_worker", "during", "shade",
       "Work in the shade where possible and wear a wide hat and loose, light-coloured clothing.",
       "ready_gov_extreme_heat"),
    _g("ow-during-work_schedule-1", "outdoor_worker", "during", "work_schedule",
       "Avoid high-energy tasks during midday heat if possible.", "ready_gov_extreme_heat",
       min_category="moderate"),
    _g("ow-during-check_others-1", "outdoor_worker", "during", "check_others",
       "Watch co-workers for signs of heat stress, especially older workers, pregnant workers and people with "
       "chronic health conditions.", "who_workplace_heat_stress"),
    _g("ow-during-escalation-1", "outdoor_worker", "during", "escalation",
       "Heat exhaustion and heat stroke need an emergency response: if a worker is confused, faints or "
       f"collapses, stop work, move them to shade, cool them and {ESCALATION_CONTACT}.",
       "who_workplace_heat_stress", "ready_gov_extreme_heat"),
    _g("ow-after-rest-1", "outdoor_worker", "after", "rest",
       "After the shift, rest in a cool place, remove extra clothing and sip water to recover.",
       "ready_gov_extreme_heat"),
    _g("ow-after-escalation-1", "outdoor_worker", "after", "escalation",
       "If cramps or exhaustion after work get worse or last more than an hour, contact a health provider or "
       "the nearest health facility.", "ready_gov_extreme_heat"),
    _g("ow-after-stay_informed-1", "outdoor_worker", "after", "stay_informed",
       "Check the forecast for the coming days and adjust work schedules to it.", "fao_extreme_heat_agrifood"),
    # ---- farmers ---------------------------------------------------------------------------
    _g("fm-before-livestock_crops-1", "farmer", "before", "livestock_crops",
       "Before hot spells, mulch to keep soil moist and plan shade for vegetable crops.",
       "fao_extreme_heat_agrifood"),
    _g("fm-before-hydration-1", "farmer", "before", "hydration",
       "Store extra water for people, animals and crops before the heat arrives.",
       "fao_extreme_heat_agrifood", "wsu_livestock_heat_wave"),
    _g("fm-before-shade-1", "farmer", "before", "shade",
       "Prepare shade for animals kept outside and make sure barns and sheds are well ventilated.",
       "wsu_livestock_heat_wave", "fao_extreme_heat_agrifood"),
    _g("fm-before-stay_informed-1", "farmer", "before", "stay_informed",
       "Follow local weather forecasts and crop advisories so you can plan ahead.", "fao_extreme_heat_agrifood"),
    _g("fm-before-escalation-1", "farmer", "before", "escalation",
       f"Know how to {ESCALATION_CONTACT}, and keep the contact of a local veterinarian or extension worker "
       "for sick animals.", "ready_gov_extreme_heat", "wsu_livestock_heat_wave"),
    _g("fm-during-hydration-1", "farmer", "during", "hydration",
       "Give animals a continuous supply of cool, clean water, and drink water regularly yourself.",
       "wsu_livestock_heat_wave", "who_heat_health_factsheet"),
    _g("fm-during-work_schedule-1", "farmer", "during", "work_schedule",
       "Do field work and handle animals in the early morning or evening, and feed cattle in cooler hours.",
       "wsu_livestock_heat_wave", "fao_extreme_heat_agrifood"),
    _g("fm-during-rest-1", "farmer", "during", "rest",
       "Take rest and water breaks in the shade during field work.", "fao_extreme_heat_agrifood"),
    _g("fm-during-shade-1", "farmer", "during", "shade",
       "Keep animals that are outside in the shade, and give priority to shade for poultry, which cannot sweat.",
       "fao_extreme_heat_agrifood", "wsu_livestock_heat_wave"),
    _g("fm-during-livestock_crops-1", "farmer", "during", "livestock_crops",
       "Irrigate in the cooler hours of the day and keep harvested produce out of the sun.",
       "fao_extreme_heat_agrifood", min_category="moderate"),
    _g("fm-during-escalation-1", "farmer", "during", "escalation",
       f"If a person is confused, faints or has hot, dry skin, {ESCALATION_CONTACT}; if animals look lethargic "
       "or have dry or sunken eyes, contact a local veterinarian.", "ready_gov_extreme_heat",
       "wsu_livestock_heat_wave"),
    _g("fm-after-livestock_crops-1", "farmer", "after", "livestock_crops",
       "After the heat, watch livestock for breathing and digestive problems.", "wsu_livestock_heat_wave"),
    _g("fm-after-hydration-1", "farmer", "after", "hydration",
       "Keep animal water clean and fresh, since warm stagnant water can grow toxic blue-green algae.",
       "wsu_livestock_heat_wave"),
    _g("fm-after-rest-1", "farmer", "after", "rest",
       "Rest in a cool place after field work and sip water to recover.", "ready_gov_extreme_heat"),
    _g("fm-after-escalation-1", "farmer", "after", "escalation",
       "Contact a local veterinarian or extension worker about animals that are still unwell after the heat.",
       "wsu_livestock_heat_wave"),
]

CATALOG: dict[str, GuidanceItem] = {item.id: item for item in _ITEMS}


def _rank(category: str | None) -> int:
    return CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)


def catalog_for(audience: str, phase: str | None = None, category: str | None = None) -> list[GuidanceItem]:
    """Items for an audience (and phase, if given) that apply at the given risk category.

    `category=None` (or an unrecognised value such as 'unknown') returns every item.
    """
    limit = _rank(category)
    return [i for i in _ITEMS
            if i.audience == audience and (phase is None or i.phase == phase) and _rank(i.min_category) <= limit]
