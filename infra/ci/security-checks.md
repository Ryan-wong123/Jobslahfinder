# Security Scan Commands

Run these from the repository root when the tools are installed. They are documented as coursework MVP commands so the checks are repeatable without committing tool secrets or scan results.

## Backend SAST

```powershell
python -m pip install bandit semgrep
bandit -r backend/app -x backend/app/tests --severity-level high
semgrep --config p/python --config p/owasp-top-ten backend/app
```

## Dependency Scanning

```powershell
python -m pip install pip-audit
pip-audit backend --strict
cd frontend
npm audit --audit-level=high
cd ..
```

## Secret Scanning

```powershell
gitleaks detect --source . --no-git --redact
```

## Container Scanning

Build images first, then scan them:

```powershell
docker compose build backend worker frontend nginx
trivy image secure-job-platform-backend:latest
trivy fs --scanners vuln,secret,config --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .
```

If a scanner reports a false positive, document the exact finding, affected file/image, reason for acceptance, expiry/review date, and compensating control in `docs/security-hardening.md`.
