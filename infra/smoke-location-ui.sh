#!/usr/bin/env bash
# Task 2-05; only the guarded tmpfs db-test is recreated. --uat leaves it for browser UAT.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
case "${1:-}" in ""|--uat) ;; *) echo "Usage: bash infra/smoke-location-ui.sh [--uat]" >&2; exit 2 ;; esac
if (( $# > 1 )); then exit 2; fi
compose=(docker compose -f compose.yaml -f compose.test.yaml -f compose.smoke.yaml --profile test)
trap '"${compose[@]}" stop web-smoke api-smoke db-test' EXIT
docker compose --profile test build api-test
docker compose build api web
"${compose[@]}" stop web-smoke api-smoke db-test
"${compose[@]}" up -d --force-recreate --wait db-test
"${compose[@]}" run --rm --no-deps migrate-smoke
"${compose[@]}" up -d --no-deps --wait api-smoke web-smoke
if [[ "${1:-}" == --uat ]]; then
  fixture_dir="$(mktemp -d /tmp/assetvision-2-05-uat.XXXXXX)"
  chmod 700 "$fixture_dir"
  "${compose[@]}" run --rm --no-deps --user "$(id -u):$(id -g)" -e UAT_FIXTURE_PATH=/uat/session.json -v "$fixture_dir:/uat" api-test python tests/smoke_location_ui.py
  echo "UAT fixture directory: $fixture_dir"
  trap - EXIT
else
  "${compose[@]}" run --rm --no-deps api-test python tests/smoke_location_ui.py
fi
