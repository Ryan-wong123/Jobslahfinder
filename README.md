# Secure AI-Assisted Job Aggregation and Application Support Platform

ICT2216 Secure Software Development project repository.

This project is a secure job aggregation and application support platform. It uses a Next.js frontend, FastAPI backend, PostgreSQL database, Redis queue/cache, worker processes, and Nginx reverse proxy.

Security is a baseline requirement. Do not commit real secrets, `.env` files, uploaded resumes, logs, backups, or generated credentials.

## Current Phase

This repository currently contains the Phase 0 through Phase 3 backend foundations:

- Docker Compose service definitions.
- FastAPI backend skeleton.
- SQLAlchemy model metadata for required tables.
- Alembic migration structure.
- Next.js TypeScript Tailwind frontend skeleton.
- Nginx reverse proxy configuration.
- Import-safe scraper modules.
- Secure backend registration, login, logout, password change, password reset token storage, profile update, and soft account deletion.
- Server-side session storage with hashed session tokens and HttpOnly cookies.
- RBAC foundations with admin route protection and ownership-check helpers.
- Audit logging for authentication, profile updates, account deletion, and denied authorization events.

Frontend profile update/delete UI, full scraping workers, recommendations, cover letters, and full admin dashboard features are intentionally left for later phases.

## Prerequisites

Install Docker Desktop before running the project:

- Docker Desktop for Windows: https://docs.docker.com/installation/windows/

Docker Desktop includes Docker Compose. You do not need to install PostgreSQL or Redis separately because they run inside Docker containers.

Check Docker is available:

```powershell
docker --version
docker compose version
```

## Start The Project

Start and show logs in the terminal:

```powershell
docker compose up --build
```

Or start in the background:

```powershell
docker compose up --build -d
```

Open the app:

```text
http://localhost:8080
```

Backend health check:

```text
http://localhost:8080/health
```

Authenticated user check after login:

```text
http://localhost:8080/api/me
```

Admin RBAC check:

```text
http://localhost:8080/api/admin/health
```

## Database Setup

After the containers are running, apply database migrations:

```powershell
docker compose run --rm backend alembic upgrade head
```

## Check Running Services

Show container status:

```powershell
docker compose ps
```

Show logs for all services:

```powershell
docker compose logs
```

Show logs for one service:

```powershell
docker compose logs backend
docker compose logs frontend
docker compose logs worker
docker compose logs beat
```

## Stop The Project

Stop containers but keep database/upload volumes:

```powershell
docker compose down
```

Stop and remove volumes, including local PostgreSQL data:

```powershell
docker compose down -v
```

Only use `docker compose down -v` when you are okay deleting the local database data.

## Rebuild After Code Changes

If dependencies or Dockerfiles changed:

```powershell
docker compose up --build
```

If only backend/frontend source changed, this also works:

```powershell
docker compose up -d --build
```

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

When using Docker, prefer:

```powershell
docker compose run --rm backend alembic upgrade head
```

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
