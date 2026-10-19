FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TORCH_HOME=/opt/weights
WORKDIR /eval
COPY infra/recognition-eval/requirements.txt /tmp/eval-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/eval-requirements.txt && python -m pip check
# Freeze the final environment separately, retaining the large CPU-wheel build cache.
COPY infra/recognition-eval/requirements.lock /tmp/eval-requirements.lock
RUN python -m pip install --no-cache-dir --no-deps -r /tmp/eval-requirements.lock && python -m pip check
COPY tools/recognition_eval /eval/tools/recognition_eval
# Explicit public weight download during build only. Benchmark itself runs --network none.
RUN python -m tools.recognition_eval prepare-weights
RUN useradd --uid 10001 --create-home evaluator && chmod -R a+rX /opt/weights
USER evaluator
ENTRYPOINT ["python", "-m", "tools.recognition_eval"]
