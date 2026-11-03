"""Stage the HeatWise coordinator as an AgentCore Runtime code bundle (CodeZip).

`backend/` stays the single source. This copies it (without tests, caches and local data)
into HeatWiseAC/app/HeatWise/, adds a top-level `main.py` entrypoint and writes the
`pyproject.toml` the `agentcore` CLI installs from (uv, aarch64 manylinux; no Docker).

Run with the dev venv python before `agentcore package` / `agentcore deploy`:
    .venv\\Scripts\\python.exe infrastructure\\scripts\\stage_agentcore_app.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "HeatWiseAC" / "app" / "HeatWise"
REQUIREMENTS = ROOT / "infrastructure" / "lambda-requirements.txt"

# Runtime deps: the Lambda asset list (same pins) minus the Lambda-only adapter, plus AgentCore.
_DROP = {"mangum"}
_EXTRA = ["bedrock-agentcore==1.25.2"]
# Account id from the current credentials, so it is never hard-coded in the repository.
ACCOUNT = boto3.client("sts").get_caller_identity()["Account"]

MAIN_PY = '''"""AgentCore Runtime entrypoint for HeatWise AI (staged; edit backend/agentcore_entry.py instead)."""
from backend.agentcore_entry import app

if __name__ == "__main__":
    app.run()
'''


def _dependencies() -> list[str]:
    deps = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and line.split("==", 1)[0].lower() not in _DROP:
            deps.append(line)
    return deps + _EXTRA


def main() -> int:
    if APP.exists():
        shutil.rmtree(APP)
    APP.mkdir(parents=True)
    shutil.copytree(
        ROOT / "backend", APP / "backend",
        ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc", ".data"),
    )
    (APP / "main.py").write_text(MAIN_PY, encoding="utf-8")
    # Least-privilege Bedrock access, same ARNs as the reviewed HeatWiseApi worker policy:
    # the Nova 2 Lite US inference profile and the three Regions it routes to.
    (APP / "bedrock-nova-policy.json").write_text(json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "InvokeNova2Lite",
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": [
                f"arn:aws:bedrock:us-east-1:{ACCOUNT}:inference-profile/us.amazon.nova-2-lite-v1:0",
                "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-lite-v1:0",
                "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-2-lite-v1:0",
                "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-2-lite-v1:0",
            ],
        }],
    }, indent=2), encoding="utf-8")
    deps = ",\n".join(f'    "{d}"' for d in _dependencies())
    (APP / "pyproject.toml").write_text(
        "[project]\n"
        'name = "heatwise-agentcore"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.13"\n'
        f"dependencies = [\n{deps},\n]\n",
        encoding="utf-8",
    )
    files = sum(1 for p in APP.rglob("*") if p.is_file())
    print(f"Staged AgentCore app: {APP} ({files} files)")
    print("Dependencies:", ", ".join(_dependencies()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
