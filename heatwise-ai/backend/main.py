"""ASGI entrypoint: `uvicorn backend.main:app --port 8000` (run from heatwise-ai/)."""

from backend.api.app import create_app

app = create_app()
