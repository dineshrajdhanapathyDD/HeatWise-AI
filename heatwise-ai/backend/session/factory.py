"""Select the assessment store from settings (Milestone 4). JSON files stay the default."""

from __future__ import annotations

from backend.config import Settings
from backend.session.store import AssessmentStore, JsonFileAssessmentStore


def build_assessment_store(settings: Settings) -> AssessmentStore:
    if settings.assessment_store == "dynamodb":
        if not settings.assessments_table_name:
            raise ValueError("ASSESSMENTS_TABLE_NAME is required when ASSESSMENT_STORE=dynamodb.")
        from backend.session.dynamodb_store import DynamoDbAssessmentStore

        return DynamoDbAssessmentStore(settings.assessments_table_name, region_name=settings.aws_region)
    return JsonFileAssessmentStore(settings.assessment_store_dir)
