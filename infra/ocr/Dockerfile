FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 HOME=/tmp/ocr-home PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
WORKDIR /app
COPY infra/ocr/prepare-system-packages.py /tmp/prepare-system-packages.py
RUN --mount=type=cache,target=/var/lib/apt/lists --mount=type=cache,target=/var/cache/apt \
    rm -f /etc/apt/apt.conf.d/docker-clean && apt-get update \
    && python /tmp/prepare-system-packages.py \
    && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 fonts-dejavu-core
FROM base AS dependencies
COPY infra/ocr/requirements.txt /tmp/ocr-requirements.txt
COPY apps/api/requirements*.txt apps/api/requirements*.lock /tmp/api-deps/
# Optional local wheel cache transport; no application secrets or runtime network needed.
ARG PIP_FIND_LINKS
ARG PIP_NO_INDEX=0
RUN python -m pip install --no-cache-dir -r /tmp/ocr-requirements.txt -r /tmp/api-deps/requirements-dev.txt -r /tmp/api-deps/requirements-dev.lock && python -m pip check
# Freeze final environment separately, retaining the large CPU-wheel installation cache.
COPY infra/ocr/requirements.lock /tmp/ocr-requirements.lock
RUN python -m pip install --no-cache-dir --no-deps -r /tmp/ocr-requirements.lock && python -m pip check
FROM dependencies AS models
COPY infra/ocr/prepare-models.py /tmp/prepare-models.py
COPY apps/api/app/ocr_weights.json /tmp/ocr_weights.json
ARG OCR_MODEL_ARCHIVE_CACHE_URL
RUN python /tmp/prepare-models.py --root /opt/ocr-models --manifest /tmp/ocr_weights.json --archive-cache-url "${OCR_MODEL_ARCHIVE_CACHE_URL}"
FROM models AS runtime
COPY apps/api /app
RUN useradd --uid 10001 --create-home ocr
USER ocr
ENTRYPOINT ["python", "-m", "app.ocr_cli"]
