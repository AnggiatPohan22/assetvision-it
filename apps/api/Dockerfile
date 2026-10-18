FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --uid 10001 --create-home app

FROM base AS runtime-dependencies
COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.txt -r requirements.lock \
    && python -m pip check

FROM runtime-dependencies AS test-dependencies
COPY requirements-dev.txt requirements-dev.lock ./
RUN python -m pip install --no-cache-dir -r requirements-dev.txt -r requirements-dev.lock \
    && python -m pip check \
    && python -m pytest --version \
    && python -m ruff --version

FROM test-dependencies AS test
COPY . .
USER app
CMD ["python", "-m", "pytest", "-q"]

# Default/final image contains only runtime dependencies.
FROM runtime-dependencies AS runtime
COPY . .
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
