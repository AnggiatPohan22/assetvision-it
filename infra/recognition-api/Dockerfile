# Explicit opt-in: choose a previously built, pinned local CPU environment.
ARG CPU_BASE=assetvision-recognition-index:3-02
FROM ${CPU_BASE}
WORKDIR /app
COPY apps/api /app
ENTRYPOINT ["uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
