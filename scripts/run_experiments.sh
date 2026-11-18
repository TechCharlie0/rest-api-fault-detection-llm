#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate

LABEL="${1:-full}"
python -m agenticapi run --config configs/default.json --label "$LABEL"
