FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir ".[scrapers]"

COPY app ./app
COPY risk_engine ./risk_engine
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /var/lib/jobapp/uploads \
    && mkdir -p /var/lib/jobapp/risk-engine \
    && chown -R appuser:appuser /var/lib/jobapp

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
