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

## Cover Letter Generation

Cover letter drafts use Gemini by default when `GEMINI_API_KEY` is configured:

```text
COVER_LETTER_GENERATION_PROVIDER=gemini
GEMINI_COVER_LETTER_MODEL=gemini-2.5-flash-lite
GEMINI_COVER_LETTER_MAX_OUTPUT_TOKENS=2048
```

The backend sends only bounded structured extraction fields and bounded job fields to Gemini. It does not send full raw resume text, log prompts, log generated drafts, or submit anything externally. If Gemini is unavailable, the backend safely falls back to the deterministic draft generator.

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

## Commands By Change Scenario

Use this section when deciding what to run after changing code. Run commands from the repository root unless a section says otherwise:

```powershell
cd C:\Users\ryan\Downloads\SSD-project
```

### First Setup Or Fresh Database

Use this after cloning the project, after `docker compose down -v`, or whenever the database volume has been deleted.

```powershell
docker compose up -d --build
docker compose run --rm backend alembic upgrade head
docker compose ps
```

Create the first admin after migrations:

```powershell
docker compose run --rm backend python -m app.cli create-initial-admin --email admin@example.com
```

### Backend Python Code Only

Use this for changes under `backend/app/` that do not add dependencies or migrations.

```powershell
docker compose build backend worker beat
docker compose up -d backend worker beat nginx
docker compose logs --tail=80 backend
```

Run backend tests:

```powershell
$env:PYTHONPATH='C:\Users\ryan\Downloads\SSD-project\backend\.test-deps;C:\Users\ryan\Downloads\SSD-project\backend'
& 'C:\Users\ryan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest
```

### Backend API Or Model Change With Migration

Use this when SQLAlchemy models or Alembic migrations changed.

```powershell
docker compose build backend worker beat
docker compose run --rm backend alembic upgrade head
docker compose up -d backend worker beat nginx
docker compose run --rm backend alembic current
```

### Worker Or Scheduled Task Change

Use this for resume extraction, scraping, Celery task, or beat schedule changes.

```powershell
docker compose build worker beat
docker compose up -d worker beat nginx
docker compose logs --tail=120 worker
docker compose logs --tail=120 beat
```

### Frontend Code Only

Use this for changes under `frontend/src/`.

```powershell
cd frontend
npm run lint
npm run build
cd ..
docker compose build frontend nginx
docker compose up -d frontend nginx
```

### Frontend Dependency Or Dockerfile Change

Use this when `frontend/package.json`, `package-lock.json`, or `frontend/Dockerfile` changed.

```powershell
docker compose build frontend nginx
docker compose up -d frontend nginx
```

### Backend Dependency Or Dockerfile Change

Use this when `backend/pyproject.toml` or `backend/Dockerfile` changed.

```powershell
docker compose build backend worker beat
docker compose up -d backend worker beat nginx
```

### Nginx Or Docker Compose Change

Use this when `docker-compose.yml` or files under `infra/nginx/` changed.

```powershell
docker compose up -d --build nginx frontend backend worker beat
docker compose ps
```

### Full Rebuild Without Deleting Data

Use this when several services changed but you want to keep local PostgreSQL data and uploaded files.

```powershell
docker compose up -d --build
docker compose ps
```

### Full Reset And Rebuild

This deletes local PostgreSQL, Redis, and uploaded resume volumes. Use only when you are okay losing local data.

```powershell
docker compose down -v
docker compose up -d --build
docker compose run --rm backend alembic upgrade head
```

### Verify Running App

```powershell
docker compose ps
docker compose logs --tail=80 backend
docker compose run --rm backend alembic current
```

Open:

```text
http://localhost:8080
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
