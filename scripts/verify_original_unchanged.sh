#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

diff -q main.py backups/original_artifacts_20261117/main.py
diff -q petstore.json backups/original_artifacts_20261117/petstore.json
diff -rq agents backups/original_artifacts_20261117/agents
diff -rq services backups/original_artifacts_20261117/services
diff -rq generated_tests backups/original_artifacts_20261117/generated_tests
printf '%s\n' "original artifacts match the backup"
