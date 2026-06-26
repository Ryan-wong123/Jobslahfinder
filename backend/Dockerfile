FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /var/lib/jobapp/uploads \
    && chown -R appuser:appuser /var/lib/jobapp

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
