FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# build deps only in the build stage; runtime keeps libpq + postgres-client (pg_dump/pg_restore)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev postgresql-client ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG APP_VERSION=1.0.0
ENV APP_VERSION=${APP_VERSION}

# non-root runtime user; writable dirs it needs
RUN useradd --system --uid 10001 --home /app appuser \
    && mkdir -p /app/storage /app/outputs /app/backups /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live',timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
