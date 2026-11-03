"""Create the Bedrock model used by all agents. Tests inject their own Model instead."""

from __future__ import annotations

from strands.models import BedrockModel

from backend.config import Settings


def build_bedrock_model(settings: Settings, temperature: float = 0.1) -> BedrockModel:
    # Low temperature: specialists should copy tool data, not improvise.
    return BedrockModel(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=temperature,
    )
