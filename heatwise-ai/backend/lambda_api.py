"""API Lambda: the FastAPI app behind API Gateway HTTP API via Mangum (Milestone 4, D-M4-2).

`lifespan="off"`: the only lifespan work is the local thread-pool shutdown, which the
Lambda path (DynamoDB jobs + async worker invoke) does not use.

Handler path: `backend.lambda_api.handler`.
"""

from __future__ import annotations

import logging
from typing import Any

from mangum import Mangum

from backend.api.app import create_app
from backend.config import Settings, get_settings

_handler: Mangum | None = None


def build_handler(settings: Settings | None = None, **create_app_kwargs: Any) -> Mangum:
    return Mangum(create_app(settings, **create_app_kwargs), lifespan="off")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    global _handler
    if _handler is None:  # cold start: build the app once per execution environment
        settings = get_settings()
        logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s", force=True)
        _handler = build_handler(settings)
    return _handler(event, context)
