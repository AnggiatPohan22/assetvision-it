#!/usr/bin/env bash
# Task3-05 smoke; only temporary db-test/photo storage are written by test fixtures.
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
"${compose[@]}" run --rm --no-deps api-test python tests/smoke_recognition.py
