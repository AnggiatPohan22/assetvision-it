#!/usr/bin/env bash
# Optional real Paddle CPU checks; generated labels only, no dev DB/photos mounted.
set -euo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
docker build --network "${OCR_BUILD_NETWORK:-default}" \
  --build-arg PIP_FIND_LINKS --build-arg PIP_NO_INDEX --build-arg OCR_MODEL_ARCHIVE_CACHE_URL \
  -f infra/ocr/Dockerfile -t assetvision-ocr:3-03 .
docker run --rm --network none --read-only --tmpfs /tmp:size=256m \
  --cpus 2 --memory 2g --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint python assetvision-ocr:3-03 -m pytest -q -s tests/test_ocr_cpu.py
