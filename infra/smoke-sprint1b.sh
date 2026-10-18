#!/usr/bin/env bash
# Sprint 0/1A/1B HTTP regression. Recreate only the dedicated tmpfs db-test service.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
compose=(docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test)
trap '"${compose[@]}" stop web-smoke api-smoke db-test' EXIT
docker compose --profile test build api-test
docker compose build api web
"${compose[@]}" stop web-smoke api-smoke db-test
"${compose[@]}" up -d --force-recreate --wait db-test
"${compose[@]}" run --rm --no-deps migrate-smoke
"${compose[@]}" up -d --no-deps --wait api-smoke web-smoke
for test in smoke_stack smoke_catalog smoke_assets smoke_asset_csv smoke_asset_ui smoke_seed_assets; do
  "${compose[@]}" run --rm --no-deps api-test python "tests/${test}.py"
done
