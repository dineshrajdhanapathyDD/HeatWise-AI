"""Environment-based configuration for HeatWise AI.

Values come from environment variables or a local `.env` file. AWS credentials are
never read from here; boto3 resolves them from the normal AWS credential chain.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    aws_region: str = Field(default="us-east-1")
    bedrock_model_id: str = Field(default="us.amazon.nova-2-lite-v1:0")

    weather_provider: Literal["open_meteo", "demo"] = Field(default="open_meteo")
    http_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    weather_stale_after_minutes: int = Field(default=90, gt=0)
    # Optional ISO-3166 alpha-2 code to restrict geocoding, e.g. "IN". Empty = worldwide.
    geocode_country_code: str | None = Field(default=None)

    agent_max_turns: int = Field(default=8, ge=1, le=50)
    agent_max_tool_calls: int = Field(default=6, ge=1, le=50)

    # Community risk: number of community vulnerability indicators needed to raise the
    # category one step. This is a configurable PROJECT HEURISTIC, not an official standard.
    risk_vulnerability_min_indicators: int = Field(default=2, ge=1, le=8)
    planner_max_tool_calls: int = Field(default=14, ge=1, le=50)
    plan_max_general_advice: int = Field(default=3, ge=0, le=10)
    # Optional, non-blocking LLM review in the Safety Agent. Pass/fail is always deterministic.
    safety_llm_review: bool = Field(default=True)
    coordinator_max_turns: int = Field(default=16, ge=1, le=50)
    coordinator_max_tool_calls: int = Field(default=10, ge=1, le=50)

    # Milestone 3 API. "offline" runs scripted agents (demos and tests only, never production).
    # "agentcore" runs the agents on the deployed AgentCore Runtime (the worker only invokes it).
    agent_mode: Literal["bedrock", "offline", "agentcore"] = Field(default="bedrock")
    agentcore_runtime_arn: str | None = Field(default=None)
    agentcore_timeout_seconds: int = Field(default=270, ge=30, le=900)
    assessment_store_dir: str = Field(default=".data/assessments")
    api_cors_origins: list[str] = Field(default=["http://localhost:5173", "http://127.0.0.1:5173"])
    api_job_workers: int = Field(default=2, ge=1, le=8)
    api_max_pending_jobs: int = Field(default=20, ge=1, le=200)

    # Milestone 4 persistence and deployment. Defaults keep the local M3 behaviour.
    assessment_store: Literal["json", "dynamodb"] = Field(default="json")
    assessments_table_name: str | None = Field(default=None)
    job_store: Literal["memory", "dynamodb"] = Field(default="memory")
    jobs_table_name: str | None = Field(default=None)
    job_dispatch: Literal["thread", "lambda"] = Field(default="thread")
    worker_function_name: str | None = Field(default=None)
    job_ttl_days: int = Field(default=7, ge=1, le=90)
    job_stale_after_seconds: int = Field(default=420, ge=60, le=3600)
    # Strands session storage for the coordinator conversation (only when a session id is given).
    session_storage: Literal["file", "s3", "none"] = Field(default="file")
    session_dir: str = Field(default=".data/sessions")
    session_bucket: str | None = Field(default=None)
    session_prefix: str = Field(default="sessions")

    # Milestone 5: file served by GET /api/evaluation. None = the packaged
    # backend/evaluation/results/evaluation-results.json.
    evaluation_results_path: str | None = Field(default=None)

    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings. Tests construct `Settings(...)` directly instead."""
    return Settings()
