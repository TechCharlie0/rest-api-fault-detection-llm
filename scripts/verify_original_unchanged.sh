#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Verify original artifacts match backup - skip gracefully if no backup exists
# (backups/ is gitignored local state; not available on clean runners)
if [ ! -d "backups/original_artifacts_20261117" ]; then
  printf '%s\n' "backup directory not found; skipping original artifact comparison (local state not available)"
  exit 0
fi

diff -q main.py backups/original_artifacts_20261117/main.py
diff -q petstore.json backups/original_artifacts_20261117/petstore.json
diff -rq agents backups/original_artifacts_20261117/agents
diff -rq services backups/original_artifacts_20261117/services
diff -rq generated_tests backups/original_artifacts_20261117/generated_tests
printf '%s\n' "original artifacts match the backup"
