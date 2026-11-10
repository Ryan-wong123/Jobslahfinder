"""Migrate a disposable PostgreSQL database and verify roles and token races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
import tempfile
import shutil

import psycopg
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]


def command(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def main():
    name = "database-security-" + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    env = {**os.environ, "POSTGRES_PASSWORD": password, "APP_DB_PASSWORD": password, "SCRAPER_DB_PASSWORD": password,"WORKER_DB_PASSWORD":password}
    image = "postgres:16-alpine@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139"
    try:
        command(["docker", "run", "-d", "--name", name, "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD",
            "-e", "APP_DB_PASSWORD", "-e", "SCRAPER_DB_PASSWORD", "-e", "WORKER_DB_PASSWORD", "-e", "POSTGRES_USER=postgres", image], env=env)
        address = command(["docker", "port", name, "5432/tcp"]).splitlines()[0]
        host, port = address.split(":")
        for attempt in range(60):
            try:
                admin = psycopg.connect(host=host, port=port, user="postgres", password=password, dbname="postgres", autocommit=True)
                break
            except psycopg.OperationalError:
                if attempt == 59:
                    raise
                time.sleep(0.5)
        dsn = f"postgresql+psycopg://postgres:{password}@{address}/postgres"
        test_env = {**env, "APP_ENV":"test", "SERVICE_ROLE":"api", "DATABASE_URL":dsn,
            "REDIS_URL":"redis://127.0.0.1:6379/15", "SESSION_SECRET":secrets.token_hex(32),
            "PASSWORD_RESET_SECRET":secrets.token_hex(32), "UPLOAD_DIR":str(ROOT/".tmp/test-uploads"),
            "ALLOWED_JOB_SOURCE_DOMAINS":"sg.jobstreet.com",
            "RISK_ENGINE_DATA_DIR":str(ROOT/".tmp/test-risk-postgres")}
        command([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT/"backend", env=test_env)
        script = (ROOT/"infra/scripts/provision-db-roles.sh").read_text()
        sql = script.split("<<'SQL'\n",1)[1].split("\nSQL",1)[0]
        command(["docker","exec","-i",name,"psql","-X","-q","-v","ON_ERROR_STOP=1","-U","postgres"], input=sql)
        admin.close()
        with psycopg.connect(host=host, port=port, user="jobapp_runtime", password=password, dbname="postgres", autocommit=True) as runtime:
            assert runtime.execute("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone() == (False,)
            for sql_attempt in ("CREATE TABLE forbidden(id int)", "DELETE FROM audit_logs", "UPDATE audit_logs SET event_type='tampered'"):
                try:
                    runtime.execute(sql_attempt)
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("Runtime privilege exceeded")
        with psycopg.connect(host=host, port=port, user="jobapp_scraper", password=password, dbname="postgres", autocommit=True) as scraper:
            for table in ("users", "resumes", "email_deliveries", "sessions", "password_reset_tokens"):
                try:
                    scraper.execute(f"SELECT * FROM {table}")  # Fixed test-only table allowlist.
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("Scraper accessed private data")
            scraper.execute("INSERT INTO audit_logs(event_type,outcome) VALUES ('scraping.test','SUCCESS') RETURNING id,created_at").fetchone()
        with psycopg.connect(host=host,port=port,user="jobapp_worker",password=password,dbname="postgres",autocommit=True) as worker:
            for table in ("users","sessions","password_reset_tokens","email_change_tokens"):
                try:worker.execute(f"SELECT * FROM {table}")
                except psycopg.errors.InsufficientPrivilege:pass
                else:raise AssertionError("Private worker accessed authentication data")
        print("PASS restricted roles: no DDL, no audit tampering, scraper cannot read private tables")

        os.environ.update(test_env)
        sys.path.insert(0,str(ROOT/"backend"))
        from app.models.account import User, PasswordResetToken
        from app.security.passwords import hash_password
        from app.security.tokens import hash_token
        from app.core.config import get_settings
        from app.services.auth import confirm_password_reset, utc_now
        settings = get_settings()
        engine = create_engine(f"postgresql+psycopg://jobapp_runtime:{password}@{address}/postgres", hide_parameters=True)
        with Session(engine) as db:
            user = User(email="race@example.test",password_hash=hash_password("BeforePassword123"),role="USER",is_active=True,failed_login_count=0,totp_enabled=False)
            db.add(user);db.flush()
            db.add(PasswordResetToken(user_id=user.id,token_hash=hash_token("R"*43,settings.password_reset_secret),expires_at=utc_now()+timedelta(minutes=5)))
            db.commit()
        def reset():
            with Session(engine) as db:
                try:
                    confirm_password_reset(db,None,settings,token="R"*43,new_password="AfterPassword456")
                    return "success"
                except ValueError:
                    return "rejected"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _:reset(),range(2)))
        assert sorted(results) == ["rejected","success"], results
        engine.dispose()
        print("PASS concurrent reset: exactly one request consumes the token")
        from app.models.job import JobSource
        from app.services.scraping import run_scraper_for_source
        engine = create_engine(dsn, hide_parameters=True)
        with Session(engine) as db:
            source = JobSource(source_name="JobStreet",base_url="https://sg.jobstreet.com",is_enabled=True)
            db.add(source);db.commit();source_id=source.id
        engine.dispose()
        engine = create_engine(f"postgresql+psycopg://jobapp_scraper:{password}@{address}/postgres", hide_parameters=True)
        with Session(engine) as db:
            source = db.get(JobSource,source_id)
            run = run_scraper_for_source(db,source=source,fetcher=lambda source:[{
                "title":"Test Engineer","company":"Test Company","external_job_id":"test-1",
                "job_url":"https://sg.jobstreet.com/job/test-1"}])
            assert run.status == "SUCCESS", run.status
        engine.dispose()
        print("PASS restricted scraper: normalization, storage, and audit insertion work")
        gpg = shutil.which("gpg") or "C:/Program Files/Git/usr/bin/gpg.exe"
        (ROOT/".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/".tmp") as directory:
            folder=Path(directory)
            key=folder/"passphrase"
            key.write_text(secrets.token_hex(32))
            dump=folder/"postgres.dump"
            with dump.open("wb") as output:
                subprocess.run(["docker","exec",name,"pg_dump","-U","postgres","-Fc"],stdout=output,check=True)
            encrypted=folder/"postgres.dump.gpg"
            restored=folder/"restored.dump"
            for args in (["--symmetric","--cipher-algo","AES256","-o",str(encrypted),str(dump)],
                         ["--decrypt","-o",str(restored),str(encrypted)]):
                command([gpg,"--batch","--yes","--pinentry-mode","loopback","--passphrase-file",str(key),*args])
            assert dump.read_bytes()==restored.read_bytes()
            command(["docker","exec",name,"createdb","-U","postgres","restore_probe"])
            with restored.open("rb") as source:
                subprocess.run(["docker","exec","-i",name,"pg_restore","-U","postgres","-d","restore_probe","--single-transaction","--exit-on-error"],stdin=source,check=True,capture_output=True)
            restored_count=command(["docker","exec",name,"psql","-U","postgres","-d","restore_probe","-tAc","SELECT count(*) FROM users"])
            assert restored_count=="1"
        print("PASS encrypted PostgreSQL backup: GPG round-trip and transactional restore retain the user record")
    finally:
        subprocess.run(["docker","rm","-f","-v",name],capture_output=True)


if __name__ == "__main__":
    main()
