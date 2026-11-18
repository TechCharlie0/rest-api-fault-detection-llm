#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate

pytest -q
ruff check agenticapi tests
mypy agenticapi
python scripts/check_secrets.py
python -m agenticapi check
python -m agenticapi run --config configs/smoke.json --label smoke
