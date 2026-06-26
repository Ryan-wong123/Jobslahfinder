# Secure AI-Assisted Job Aggregation and Application Support Platform

ICT2216 Secure Software Development project repository.

This project is a secure job aggregation and application support platform. It uses a Next.js frontend, FastAPI backend, PostgreSQL database, Redis queue/cache, worker processes, and Nginx reverse proxy.

Security is a baseline requirement. Do not commit real secrets, `.env` files, uploaded resumes, logs, backups, or generated credentials.

## Current Phase

This repository currently contains the Phase 0 and Phase 1 skeleton:

- Docker Compose service definitions.
- FastAPI backend skeleton.
- SQLAlchemy model metadata for required tables.
- Alembic migration structure.
- Next.js TypeScript Tailwind frontend skeleton.
- Nginx reverse proxy configuration.
- Import-safe scraper modules.

Authentication, authorization, account flows, scraping workers, resume upload processing, recommendations, cover letters, and admin features are intentionally left for later phases.

## Local Setup

1. Copy `.env.example` to `.env`.
2. Replace all placeholder values in `.env` with local development values.
3. Start services:

```powershell
docker compose up --build
```

The Nginx reverse proxy listens on `http://localhost:8080` by default.

## Backend Development

From the `backend/` directory:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

Run the backend directly after configuring environment variables:

```powershell
python -m uvicorn app.main:app --reload
```

## Database Migrations

From the `backend/` directory:

```powershell
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Do not run migrations against production without reviewing generated SQL.

## Frontend Development

From the `frontend/` directory:

```powershell
npm install
npm run dev
```

The frontend expects API traffic to go through the reverse proxy in deployment.

## Security Notes

- Use `.env.example` only for variable names and placeholders.
- Store uploaded resumes outside public web roots.
- PostgreSQL and Redis are internal Docker services and are not exposed through host ports.
- Backend routes must enforce authentication, authorization, validation, safe errors, and audit logging when implemented.
- Scrapers must not execute at import time.
