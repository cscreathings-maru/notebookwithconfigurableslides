# Orchestrator backend — FastAPI app + Arq worker share this image.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY . .

EXPOSE 8000

# API server. The worker overrides this command in docker-compose
# (`arq src.workers.WorkerSettings`).
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
