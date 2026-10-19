#!/usr/bin/env bash
# Usage: bash infra/evaluate-recognition.sh NEW_REPORT_FILE
# Serial with all db-test writers. Synthetic fixtures only; no development writes.
set -euo pipefail
if (( $# != 1 )); then echo "Usage: $0 NEW_REPORT_FILE" >&2; exit 2; fi
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
report_parent="$(realpath -e -- "$(dirname -- "$1")")"
report_file="$report_parent/$(basename -- "$1")"
[[ ! -e "$report_file" ]] || { echo "Report already exists" >&2; exit 2; }
compose=(docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml -f compose.recognition-eval.yaml --profile test)
trap '"${compose[@]}" stop web-smoke api-smoke db-test' EXIT
docker compose --profile test build api-test
docker compose build api web
"${compose[@]}" stop web-smoke api-smoke db-test
"${compose[@]}" up -d --force-recreate --wait db-test
"${compose[@]}" run --rm --no-deps migrate-smoke
"${compose[@]}" up -d --force-recreate --no-deps --wait api-smoke web-smoke
python3 infra/recognition_evaluation_profile.py "$report_file"
