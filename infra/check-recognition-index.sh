#!/usr/bin/env bash
# Optional CPU integration checks; no database or development storage mounted.
set -euo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
docker build -f infra/recognition-eval/Dockerfile -t assetvision-recognition-eval:3-01 .
docker build -f infra/recognition-index/Dockerfile -t assetvision-recognition-index:3-02 .
docker run --rm --network none --read-only --tmpfs /tmp:size=256m \
  --cpus 2 --memory 2g --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint python assetvision-recognition-index:3-02 -m pytest -q tests/test_recognition_cpu.py
