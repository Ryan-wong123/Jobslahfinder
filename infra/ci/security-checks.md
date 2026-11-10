# Security Scan Commands

Run these from the repository root when the tools are installed. They are documented as coursework MVP commands so the checks are repeatable without committing tool secrets or scan results.

## Backend SAST

```powershell
python -m pip install bandit semgrep
bandit -r backend/app backend/risk_engine -x backend/app/tests,backend/risk_engine/test --severity-level high
semgrep --config p/python --config p/owasp-top-ten backend/app
```

## Dependency Scanning

```powershell
python -m pip install pip-audit
pip-audit -r backend/requirements.lock --no-deps --disable-pip --strict
pip-audit -r backend/requirements-scraper.lock --no-deps --disable-pip --strict
cd frontend
npm audit --audit-level=high
cd ..
```

## Secret Scanning

```powershell
gitleaks detect --source . --redact
```

## Container Scanning

Build images first, then scan them:

```powershell
docker compose build backend scraper frontend
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 jobslahfinder-backend:local
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 jobslahfinder-scraper:local
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 jobslahfinder-frontend:local
trivy fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .
```

If a scanner reports a false positive, document the exact finding, affected file/image, reason for acceptance, expiry/review date, and compensating control in `docs/security-hardening.md`.

For a daemonless local scan, export a built image with `docker save -o image.tar <image>`
and run `trivy image --input image.tar`. A scanner container does not need the host
Docker socket. Install the scanner versions in `requirements-scanners.lock` with
`pip install --require-hashes -r infra/ci/requirements-scanners.lock`.
