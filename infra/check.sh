#!/usr/bin/env bash
# Run from Ubuntu WSL2: bash infra/check.sh [--postgres]
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

case "${1:-}" in
  "") ;;
  --postgres) ;;
  *) echo "Usage: bash infra/check.sh [--postgres]" >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  echo "Usage: bash infra/check.sh [--postgres]" >&2
  exit 2
fi

# Dedicated images include dev tools; runtime api/web images intentionally do not.
# No source or node_modules bind mount can hide image-installed dependencies.
docker compose --profile test build api-test web-check
docker compose --profile test run --rm --no-deps api-test python -m pip check
docker compose --profile test run --rm --no-deps api-test python -m pytest -q
docker compose --profile test run --rm --no-deps api-test python -m ruff check .
docker compose --profile test run --rm --no-deps web-check npm run check

if [[ "${1:-}" == "--postgres" ]]; then
  # Only db-test (tmpfs) is used; never point tests at the application database.
  trap 'docker compose -f compose.yaml -f compose.test.yaml --profile test stop db-test' EXIT
  docker compose -f compose.yaml -f compose.test.yaml --profile test run --rm api-test python -m pytest -q
fi
