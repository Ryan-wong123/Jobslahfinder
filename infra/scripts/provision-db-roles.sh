#!/usr/bin/env bash
# Operator-only, idempotent role provisioning for new and existing databases.
# Run on the VM after migrations; passwords are read from the postgres process
# environment, never interpolated by a shell or passed on the command line.
set -Eeuo pipefail
docker compose exec -T postgres sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
\getenv app_password APP_DB_PASSWORD
\getenv scraper_password SCRAPER_DB_PASSWORD
\getenv worker_password WORKER_DB_PASSWORD
\getenv owner POSTGRES_USER
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
SELECT 'CREATE ROLE jobapp_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='jobapp_runtime') \gexec
SELECT 'CREATE ROLE jobapp_scraper LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='jobapp_scraper') \gexec
SELECT 'CREATE ROLE jobapp_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='jobapp_worker') \gexec
SELECT format('ALTER ROLE jobapp_runtime PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE jobapp_scraper PASSWORD %L', :'scraper_password') \gexec
SELECT format('ALTER ROLE jobapp_worker PASSWORD %L', :'worker_password') \gexec
ALTER ROLE jobapp_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE jobapp_scraper NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE jobapp_worker NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO jobapp_runtime, jobapp_scraper, jobapp_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO jobapp_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO jobapp_runtime;
REVOKE ALL ON audit_logs FROM jobapp_runtime;
GRANT SELECT, INSERT ON audit_logs TO jobapp_runtime;
REVOKE ALL ON alembic_version FROM jobapp_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM jobapp_scraper;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM jobapp_scraper;
GRANT SELECT ON job_sources TO jobapp_scraper;
GRANT SELECT, INSERT, UPDATE ON job_postings, scraping_runs TO jobapp_scraper;
GRANT INSERT ON audit_logs TO jobapp_scraper;
GRANT SELECT (id, created_at) ON audit_logs TO jobapp_scraper;
GRANT USAGE ON SEQUENCE job_postings_id_seq, scraping_runs_id_seq, audit_logs_id_seq TO jobapp_scraper;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM jobapp_worker;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM jobapp_worker;
GRANT SELECT ON resumes TO jobapp_worker;
GRANT SELECT, INSERT, UPDATE ON resume_extractions TO jobapp_worker;
GRANT SELECT, UPDATE ON email_deliveries TO jobapp_worker;
GRANT INSERT ON audit_logs TO jobapp_worker;
GRANT SELECT (id, created_at) ON audit_logs TO jobapp_worker;
GRANT USAGE ON SEQUENCE resume_extractions_id_seq, audit_logs_id_seq TO jobapp_worker;
SQL
echo "Restricted database roles provisioned."
