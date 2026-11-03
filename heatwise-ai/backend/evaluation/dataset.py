"""Evaluation datasets (synthetic): scenarios, knowledge test and adversarial plan items.

All three files live in `backend/evaluation/datasets/` and are labelled synthetic. Scenario
weather is served by `backend.evaluation.provider.ScenarioWeatherProvider`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from backend.models.risk import CommunityProfile

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
SCENARIOS_PATH = DATASETS_DIR / "scenarios-v1.json"
KNOWLEDGE_PATH = DATASETS_DIR / "knowledge-test-v1.json"
ADVERSARIAL_PATH = DATASETS_DIR / "adversarial-v1.json"

ErrorCode = Literal["provider_unavailable", "provider_timeout", "location_not_found"]


class FixtureLocation(BaseModel):
    name: str
    admin1: str | None = None
    country: str | None = None
    country_code: str | None = None
    latitude: float
    longitude: float
    timezone: str | None = None


class FixtureCurrent(BaseModel):
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_kmh: float | None = None
    precipitation_mm: float | None = None


class FixtureDay(BaseModel):
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None
    apparent_temperature_max_c: float | None = None
    precipitation_sum_mm: float | None = None
    uv_index_max: float | None = None
    relative_humidity_max_pct: float | None = None


class ScenarioWeather(BaseModel):
    location: FixtureLocation
    current: FixtureCurrent | None = None
    current_error: ErrorCode | None = None
    forecast_days: list[FixtureDay] | None = None
    forecast_error: ErrorCode | None = None
    observed_minutes_ago: int = 10
    geocode_error: ErrorCode | None = None


class ScenarioExpected(BaseModel):
    status: Literal["complete", "needs_human_review", "incomplete"]
    risk_category: str
    verification_status: Literal["passed", "failed", "not_run"]
    path: list[str]
    error_code: str | None = None
    plan_language: str | None = None
    requested_language: str | None = None


class Scenario(BaseModel):
    id: str
    title: str
    location: str
    forecast_days: int = 3
    profile: CommunityProfile = Field(default_factory=CommunityProfile)
    weather: ScenarioWeather
    expected: ScenarioExpected
    derivation: dict
    tags: list[str] = Field(default_factory=list)


class ScenarioDataset(BaseModel):
    dataset_version: str
    synthetic: bool
    label: str
    notes: str | None = None
    scenarios: list[Scenario]


class KnowledgeQuestion(BaseModel):
    id: str
    question: str
    options: dict[str, str]
    answer: Literal["A", "B", "C", "D"]
    catalog_item_id: str
    source_ids: list[str]
    answer_evidence: str


class KnowledgeTest(BaseModel):
    dataset_version: str
    synthetic: bool
    label: str
    questions: list[KnowledgeQuestion]


class AdversarialCase(BaseModel):
    id: str
    kind: Literal["general_educational", "sourced"]
    text: str
    source_ids: list[str] = Field(default_factory=list)
    expected_rule: str | None = None


class AdversarialDataset(BaseModel):
    dataset_version: str
    synthetic: bool
    label: str
    unsafe: list[AdversarialCase]
    controls: list[AdversarialCase]


def load_scenarios(path: Path = SCENARIOS_PATH) -> ScenarioDataset:
    return ScenarioDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_knowledge_test(path: Path = KNOWLEDGE_PATH) -> KnowledgeTest:
    return KnowledgeTest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_adversarial(path: Path = ADVERSARIAL_PATH) -> AdversarialDataset:
    return AdversarialDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))
