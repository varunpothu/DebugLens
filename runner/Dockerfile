FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY app ./app
COPY tests ./tests
RUN python -m pip install --upgrade pip \
    && python -m pip install ".[dev]" \
    && python -m pip uninstall -y debuglens
COPY runner/worker.py /opt/debuglens-worker/worker.py
RUN useradd --system --uid 10001 --no-create-home worker \
    && mkdir -p /workspace \
    && chown worker:worker /workspace
USER 10001:10001
WORKDIR /workspace
ENV DEBUGLENS_WORKSPACE=/workspace
ENTRYPOINT ["python", "/opt/debuglens-worker/worker.py"]
