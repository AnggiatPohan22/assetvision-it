#!/usr/bin/env bash
# HTTP CSV smoke uses only isolated test DB/storage, never development data.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
compose=(docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test)
trap '"${compose[@]}" stop web-smoke api-smoke db-test' EXIT
docker compose --profile test build api-test
docker compose build api web
"${compose[@]}" up -d --wait web-smoke
"${compose[@]}" run --rm --no-deps api-test python tests/smoke_asset_csv.py
