# Secure AI-Assisted Job Aggregation and Application Support Platform

This project is a secure job aggregation and application support platform. It uses a Next.js frontend, FastAPI backend, PostgreSQL database, Redis queue/cache, worker processes, and Nginx reverse proxy.

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

## Resume Extraction

Resume skill, education, and experience extraction uses Gemini by default. Configure these backend and worker environment variables in `.env`:

```text
RESUME_EXTRACTION_PROVIDER=gemini
GEMINI_RESUME_MODEL=gemini-2.5-flash-lite
GEMINI_API_KEY=replace-with-your-google-ai-api-key
```

For offline development or tests, set `RESUME_EXTRACTION_PROVIDER=local` to use the built-in deterministic parser. The worker sends only bounded extracted resume text to Gemini and stores the validated structured fields, not the full prompt or raw resume text.

## Database Setup

After the containers are running, apply database migrations:

```powershell
docker compose run --rm backend alembic upgrade head
```

## Initial Admin Account

Create the first administrator only after migrations have been applied:

```powershell
docker compose run --rm backend python -m app.cli create-initial-admin --email admin@example.com
```

The command prompts for the password twice. Do not pass the admin password on the command line, commit it to `.env`, or store it in documentation. The backend validates the password strength, stores only an Argon2id password hash, creates an audit log entry, and refuses to create another initial admin after an admin already exists.

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
