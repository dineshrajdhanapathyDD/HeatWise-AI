"""HeatWise AI CDK app (Milestone 4). Ends at `cdk synth`; deploying is a separate, manual step.

Stacks: HeatWiseData, HeatWiseApi and, with `-c heatwise:frontend=true`, HeatWiseFrontend.
Build the Lambda asset first: `.venv\\Scripts\\python.exe infrastructure\\scripts\\build_lambda_asset.py`.
"""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

INFRA = Path(__file__).resolve().parent
ROOT = INFRA.parent
for path in (str(ROOT), str(INFRA)):
    if path not in sys.path:
        sys.path.insert(0, path)

import aws_cdk as cdk  # noqa: E402

from stacks.api_stack import HeatWiseApiStack  # noqa: E402
from stacks.data_stack import HeatWiseDataStack  # noqa: E402
from stacks.frontend_stack import HeatWiseFrontendStack  # noqa: E402


def _flag(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (INFRA / p).resolve()


def build_app(context_overrides: dict[str, Any] | None = None) -> cdk.App:
    app = cdk.App(context=context_overrides) if context_overrides else cdk.App()
    ctx = app.node.try_get_context

    def need(key: str) -> Any:
        value = ctx(key)
        if value is None:
            raise ValueError(f"Missing CDK context value {key!r} (see infrastructure/cdk.json)")
        return value

    region = need("heatwise:region")
    removal = need("heatwise:removal")
    asset_dir = _resolve(need("heatwise:lambda_asset_dir"))
    if not (asset_dir / "backend").is_dir():
        raise FileNotFoundError(
            f"Lambda asset not found at {asset_dir}: run "
            "python infrastructure/scripts/build_lambda_asset.py first"
        )
    cors = need("heatwise:cors_origins")
    if isinstance(cors, str):
        import json
        cors = json.loads(cors)

    env = cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=region)
    data = HeatWiseDataStack(
        app, "HeatWiseData", env=env, removal=removal,
        description="HeatWise AI data - DynamoDB tables and the sessions bucket",
    )
    api = HeatWiseApiStack(
        app, "HeatWiseApi", env=env, data=data,
        asset_dir=str(asset_dir),
        model_id=need("heatwise:model_id"),
        cors_origins=list(cors),
        version=_version(),
        log_retention_days=int(need("heatwise:log_retention_days")),
        throttle_rate=float(need("heatwise:throttle_rate")),
        throttle_burst=int(need("heatwise:throttle_burst")),
        max_pending_jobs=int(need("heatwise:max_pending_jobs")),
        # Optional: run the agents on AgentCore Runtime (pass -c heatwise:agentcore_runtime_arn=<arn>).
        agentcore_runtime_arn=ctx("heatwise:agentcore_runtime_arn") or None,
        description="HeatWise AI API - Lambda functions and HTTP API",
    )
    if _flag(ctx("heatwise:frontend")):
        HeatWiseFrontendStack(
            app, "HeatWiseFrontend", env=env, api=api, removal=removal,
            log_retention_days=int(need("heatwise:log_retention_days")),
            dist_dir=str(_resolve(need("heatwise:frontend_dist"))),
            description="HeatWise AI web app - private S3 site behind CloudFront",
        )
    cdk.Tags.of(app).add("Project", "HeatWiseAI")
    return app


if __name__ == "__main__":
    build_app().synth()
