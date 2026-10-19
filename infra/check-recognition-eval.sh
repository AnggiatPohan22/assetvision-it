#!/usr/bin/env bash
# Standalone tests; no Compose, application credentials, DB or upload volume.
set -euo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
docker build -f infra/recognition-eval/Dockerfile -t assetvision-recognition-eval:3-01 .
docker run --rm --network none --read-only --tmpfs /tmp:size=256m \
  --cpus 2 --memory 2g --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint python assetvision-recognition-eval:3-01 \
  -m unittest discover -s tools/recognition_eval/tests -v
