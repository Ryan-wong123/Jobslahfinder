FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS runtime

LABEL org.opencontainers.image.source="https://github.com/Ryan-wong123/Jobslahfinder"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Apply signed distribution security updates even when the base digest predates
# a newly published fix. Release images are scanned and deployed by digest.
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends bubblewrap \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY app ./app
COPY risk_engine ./risk_engine
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /var/lib/jobapp/uploads \
    && mkdir -p /var/lib/jobapp/risk-engine \
    && chown -R appuser:appuser /var/lib/jobapp
RUN chmod 700 /var/lib/jobapp/uploads /var/lib/jobapp/risk-engine

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Browser tooling is only available to the restricted scraping worker.
FROM runtime AS scraper
USER root
COPY requirements-scraper.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --require-hashes -r requirements-scraper.lock
USER appuser

FROM runtime AS final
