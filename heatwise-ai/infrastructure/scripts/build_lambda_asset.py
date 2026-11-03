"""Build the Lambda code asset without Docker (Milestone 4, D-M4-4).

Installs the runtime dependencies as aarch64 manylinux or pure-Python wheels for Python 3.13
into infrastructure/build/lambda with `uv pip install --target`, constrained to the versions in
the dev venv, then copies the `backend` package (without tests and caches). Fails if the
unzipped size exceeds the Lambda limit of 262,144,000 bytes.

Run from anywhere with the dev venv python:
    .venv\\Scripts\\python.exe infrastructure\\scripts\\build_lambda_asset.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infrastructure"
OUT = INFRA / "build" / "lambda"
REQUIREMENTS = INFRA / "lambda-requirements.txt"
MAX_UNZIPPED_BYTES = 262_144_000
_SKIP_PREFIXES = ("-e", "heatwise-ai", "heatwise_ai", "pywin32")


def _dev_python() -> Path:
    windows = ROOT / ".venv" / "Scripts" / "python.exe"
    return windows if windows.exists() else ROOT / ".venv" / "bin" / "python"


def _constraints() -> str:
    """`uv pip freeze` of the dev venv, minus editable/local and Windows-only packages."""
    frozen = subprocess.run(
        ["uv", "pip", "freeze", "--python", str(_dev_python())],
        check=True, capture_output=True, text=True,
    ).stdout
    lines = [
        line for line in frozen.splitlines()
        if line.strip() and not line.lower().startswith(_SKIP_PREFIXES)
    ]
    return "\n".join(lines) + "\n"


def _tree_size(path: Path) -> tuple[int, int]:
    files = total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            files += 1
            total += (Path(dirpath) / name).stat().st_size
    return files, total


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "constraints.txt"
        constraints.write_text(_constraints(), encoding="utf-8")
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True)
        subprocess.run(
            [
                "uv", "pip", "install",
                "--target", str(OUT),
                "--python-platform", "aarch64-manylinux_2_28",
                "--python-version", "3.13",
                "--only-binary", ":all:",
                "-r", str(REQUIREMENTS),
                "-c", str(constraints),
            ],
            check=True,
        )
    shutil.copytree(
        ROOT / "backend", OUT / "backend",
        ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"),
    )
    # A unique marker per build gives every build a new CDK asset hash. Without it, a deploy
    # whose staging copy was interrupted can upload a partial zip under the full asset's hash,
    # and later deploys skip the upload ("no changes"). This happened on the first deploy.
    (OUT / "BUILD_ID.txt").write_text(
        f"heatwise-ai lambda asset built {datetime.now(timezone.utc).isoformat()}\n", encoding="ascii"
    )
    files, total = _tree_size(OUT)
    print(f"Lambda asset: {OUT}")
    print(f"Files: {files}; unzipped size: {total} bytes ({total / 1024 / 1024:.1f} MiB)")
    if total > MAX_UNZIPPED_BYTES:
        print(f"ERROR: asset exceeds the Lambda unzipped limit of {MAX_UNZIPPED_BYTES} bytes",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
