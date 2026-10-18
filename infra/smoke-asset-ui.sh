#!/usr/bin/env bash
# Frontend SSR and real API smoke; uses only db-test tmpfs and synthetic data.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
compose=(docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test)
trap '"${compose[@]}" stop web-smoke api-smoke db-test' EXIT
docker compose --profile test build api-test
docker compose build api web
"${compose[@]}" up -d --wait web-smoke
"${compose[@]}" run --rm --no-deps api-test python tests/smoke_asset_ui.py
