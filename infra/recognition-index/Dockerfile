# Build the explicit CPU evaluation image first; never add torch to the default API.
FROM assetvision-recognition-eval:3-01 AS runtime
USER root
WORKDIR /app
COPY apps/api/requirements*.txt apps/api/requirements*.lock /tmp/api-deps/
RUN python -m pip install --no-cache-dir -r /tmp/api-deps/requirements-dev.txt -r /tmp/api-deps/requirements-dev.lock && python -m pip check
COPY apps/api /app
ENV TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor-index
USER evaluator
ENTRYPOINT ["python", "-m", "app.recognition_cli"]
