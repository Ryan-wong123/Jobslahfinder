# Production Deployment Runbook (AWS EC2 + Docker Compose + Let's Encrypt)

A start-to-finish guide for putting Jobslahfinder on the internet, from creating the accounts to automatic
deploys from GitHub. It contains no secrets: wherever a value is secret you generate or paste it yourself on
the server, and it never goes into git or chat.

**How production is laid out**

```
Internet --443/80--> Nginx (TLS, rate limits, headers)
                       |-- /            -> Next.js frontend   (internal)
                       |-- /api/*       -> FastAPI backend     (internal)
                       `-- /risk-engine -> backend risk engine (internal)
FastAPI backend + Celery worker + Celery beat -> PostgreSQL, Redis (internal only, never published)
Resume files live in a Docker volume, outside any web root.
```

Production runs `docker-compose.yml` + `docker-compose.prod.yml` (selected by `COMPOSE_FILE` in the server's
`.env`). Only ports 80 and 443 are public; SSH (22) is limited to your own IP.

**Time and cost.** About 2 to 3 hours the first time. Costs: one `t3.medium` EC2 instance, a small disk, an
Elastic IP, and a domain (about US$10 a year). Gemini (free tier) and Brevo (free tier) cost nothing at small scale.

**Sections**

1. [Accounts you need](#1-accounts-you-need)
2. [AWS account](#2-aws-account)
3. [Domain and DNS](#3-domain-and-dns)
4. [Launch the server](#4-launch-the-server)
5. [Connect with SSH](#5-connect-with-ssh)
6. [Install the code and tools](#6-install-the-code-and-tools)
7. [Third-party services (email and AI)](#7-third-party-services-email-and-ai)
8. [Configure `.env`](#8-configure-env)
9. [Get the HTTPS certificate](#9-get-the-https-certificate)
10. [Create the database and admin, start everything](#10-create-the-database-and-admin-start-everything)
11. [First login and feature checks](#11-first-login-and-feature-checks)
12. [Backups and restore test](#12-backups-and-restore-test)
13. [Automatic deploys from GitHub](#13-automatic-deploys-from-github-aws-systems-manager)
14. [Day-to-day operations](#14-day-to-day-operations)
15. [Troubleshooting](#15-troubleshooting)
16. [Reference](#16-reference)

Conventions: commands marked **(PC)** run on your own computer (PowerShell on Windows). Commands marked
**(server)** run over SSH on the EC2 instance. Mixing them up is the most common mistake (see
[Troubleshooting](#15-troubleshooting)). A server prompt looks like `ubuntu@ip-172-31-...:~$`; a Windows prompt
looks like `PS C:\Users\you>`.

---

## 1. Accounts you need

| Account | Sign-up link | Used for |
| --- | --- | --- |
| AWS | https://portal.aws.amazon.com/billing/signup | Server (EC2), Elastic IP, backups (S3), deploy role (IAM, SSM) |
| Domain registrar | https://www.namecheap.com, https://porkbun.com, https://dash.cloudflare.com/sign-up, or free https://www.duckdns.org | The website address |
| Google AI Studio | https://aistudio.google.com/apikey | Gemini key for resume extraction and cover letters |
| Brevo (or another SMTP provider) | https://www.brevo.com | Password-reset emails |
| GitHub | https://github.com | Code, CI, automatic deploys |
| MaxMind (optional) | https://www.maxmind.com/en/geolite2/signup | Country/impossible-travel check in the risk engine |

Let's Encrypt (the HTTPS certificate) needs no sign-up; the setup script requests it for you.

You also need on your PC: Windows PowerShell (or any terminal with `ssh`) and a browser.

---

## 2. AWS account

1. Sign up at https://portal.aws.amazon.com/billing/signup (email, card, phone verification, **Basic** support plan).
2. Sign in to https://console.aws.amazon.com as the root user.
3. **Turn on MFA for the root user:** account name (top right) -> **Security credentials** -> **Assign MFA device** -> authenticator app.
4. **Set a spending alert:** https://console.aws.amazon.com/billing/home#/budgets -> **Create budget** (a "Zero spend" or about US$30/month budget) with your email.
5. Set the **region** (top right) to **Asia Pacific (Singapore) `ap-southeast-1`**. Use the same region for everything below.

---

## 3. Domain and DNS

You need a hostname that points at the server's permanent IP. Use a subdomain such as `jobs.yourdomain.com`
(the certificate and Nginx are configured for exactly one hostname; `www` is **not** covered).

**Buy a domain** at one of the registrars above, or for a free demo create `yourname.duckdns.org` at
https://www.duckdns.org (sign in with GitHub/Google, type a name, **add domain**).

You create the DNS record in [section 4](#43-give-the-server-a-permanent-ip-and-point-the-domain-at-it) once you
have the IP. The record is:

| Type | Name/Host | Value | TTL |
| --- | --- | --- | --- |
| `A` | `jobs` (gives `jobs.yourdomain.com`) | the Elastic IP | 300 / Auto |

Provider notes:

- **Cloudflare:** set the record to **DNS only** (grey cloud), not Proxied. The proxy breaks certificate issuance and real client-IP detection.
- **Namecheap:** Domain List -> Manage -> **Advanced DNS** -> Add New Record -> A Record.
- **Porkbun:** Domain Management -> **DNS** -> Type A.
- **DuckDNS:** paste the IP in the "current ip" box and click **update ip**.
- **Route 53:** Hosted zones -> your zone -> Create record (A, simple routing). If the domain was bought elsewhere, copy the four `NS` values into the registrar's nameserver settings.

---

## 4. Launch the server

### 4.1 EC2 instance

1. Open https://console.aws.amazon.com/ec2 (region Singapore) -> **Launch instance**.
2. **Name:** `jobslahfinder-prod`.
3. **Image:** Ubuntu -> **Ubuntu Server 24.04 LTS**.
4. **Instance type:** `t3.medium` (2 vCPU, 4 GB). `t3.small` is too tight for the worker (it bundles Chromium).
5. **Key pair:** **Create new key pair** -> name `jobslahfinder-key` -> RSA -> `.pem` -> Create. The download happens **once**: confirm the file saved and note where. Treat it like a password: never commit it, email it or paste it into chat.
6. **Network settings -> Edit:** create a security group `jobslahfinder-sg` with exactly these inbound rules:

   | Type | Port | Source |
   | --- | --- | --- |
   | SSH | 22 | **My IP** |
   | HTTP | 80 | Anywhere (`0.0.0.0/0`) |
   | HTTPS | 443 | Anywhere (`0.0.0.0/0`) |

   Add nothing else. The AWS banner "rules with source 0.0.0.0/0 allow all IP addresses" refers to ports 80/443, which must be public; it is expected.
7. **Storage:** 30 GiB `gp3`.
8. **Launch instance** and wait for "Running".

### 4.2 Instance IAM role (needed later for backups and deploys)

1. IAM -> Roles -> **Create role** -> AWS service -> **EC2** -> attach **AmazonSSMManagedInstanceCore** -> name `jobapp-ec2-role` -> Create.
2. EC2 -> your instance -> **Actions -> Security -> Modify IAM role** -> select `jobapp-ec2-role` -> Update.

(If your instance already has a role, just attach the policy to it.)

### 4.3 Give the server a permanent IP and point the domain at it

1. EC2 -> **Elastic IPs** -> **Allocate Elastic IP address** -> Allocate -> select it -> **Actions -> Associate Elastic IP address** -> choose the instance -> Associate. An unattached Elastic IP costs money; keep it attached.
2. Create the DNS `A` record from [section 3](#3-domain-and-dns) with this IP.
3. **(PC)** wait until the name resolves to the IP:

   ```powershell
   nslookup jobs.yourdomain.com
   ```

   Expected: an `Address:` line equal to your Elastic IP. If it is missing, wait (up to an hour) and retry. Do not continue until it matches: certificate issuance fails otherwise.

---

## 5. Connect with SSH

**(PC)**, in the folder that contains the `.pem` file:

```powershell
cd C:\Users\you\Documents
ssh -i .\jobslahfinder-key.pem ubuntu@<ELASTIC_IP>
```

Type `yes` the first time. Success looks like the Ubuntu welcome banner and a prompt `ubuntu@ip-172-31-...:~$`.

If Windows complains `UNPROTECTED PRIVATE KEY FILE` / `Bad permissions`, strip everything except your own account:

```powershell
icacls .\jobslahfinder-key.pem /inheritance:r
icacls .\jobslahfinder-key.pem /grant:r "${env:USERNAME}:(R)"
icacls .\jobslahfinder-key.pem        # must list only your own user
```

macOS/Linux: `chmod 400 jobslahfinder-key.pem`. More SSH problems: [Troubleshooting](#ssh-and-your-pc).

Type `exit` to leave the server and return to your PC.

---

## 6. Install the code and tools

**(server)**

```bash
sudo mkdir -p /opt/jobslahfinder && sudo chown ubuntu:ubuntu /opt/jobslahfinder
git clone https://github.com/Ryan-wong123/Jobslahfinder.git /opt/jobslahfinder
cd /opt/jobslahfinder
bash infra/scripts/bootstrap-vm.sh
```

(Use your own fork or repository URL. For a private repository Git asks for your username and a personal access
token as the password: https://github.com/settings/tokens -> Generate new token (classic) -> tick `repo`.)

`bootstrap-vm.sh` takes a few minutes. It installs Docker, git and the AWS CLI, creates the root-only backup
directory `/var/backups/jobapp`, enables automatic security updates, installs the **root cron jobs** (backup at
02:30 and certificate renewal at 03:17 and 15:17) and creates `.env` from `.env.example` (mode 600). If a purple
"restart services" screen appears, press Enter.

Now **log out and back in** so the `docker` group applies:

```bash
exit
```

**(PC)** reconnect with the same `ssh` command, then **(server)**:

```bash
docker ps
```

Expected: an empty table with the headers `CONTAINER ID  IMAGE  COMMAND ...` and no permission error.

---

## 7. Third-party services (email and AI)

### 7.1 Email: Brevo SMTP (free)

The backend refuses to start in production without SMTP settings, and password reset needs email.

1. Sign up at https://www.brevo.com and sign in at https://app.brevo.com.
2. **SMTP & API -> SMTP** tab. Note the server `smtp-relay.brevo.com`, port `587`, and the **Login** (looks like `a1b2c3001@smtp-brevo.com`; it is **not** your email address).
3. Click **Generate a new SMTP key**, name it, and copy it at once (starts `xsmtpsib-`; shown once). Use this **SMTP key**, not an API key and not your account password.
4. **Senders, Domains & Dedicated IPs -> Senders -> Add a sender**, enter an address you can read, and click the confirmation link Brevo emails you. Only a **verified** sender works: mail from an unverified address is silently dropped.
5. If Brevo says SMTP is not activated for your account, ask their in-app support to enable it.

You will enter: `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_USERNAME` (the Login), `SMTP_PASSWORD` (the SMTP key), `SMTP_FROM_EMAIL` (the verified sender).

Alternatives: Amazon SES (best if you own the domain; needs DKIM/SPF DNS records and a request for production access; SMTP host `email-smtp.ap-southeast-1.amazonaws.com`), or Gmail with an app password (https://myaccount.google.com/apppasswords; demo only, often lands in spam).

### 7.2 AI: Gemini API key

1. Go to https://aistudio.google.com/apikey -> **Create API key** and copy it.
2. You will enter it as `GEMINI_API_KEY`. Never commit or share it.
3. **Check the model name works before relying on it.** Google retires model names, and an old name returns `404` even if it still appears in the model list. After `.env` is configured (section 8), **(server)**:

   ```bash
   cd /opt/jobslahfinder
   set -a; . ./.env; set +a
   for m in gemini-3.5-flash-lite gemini-3.1-flash-lite; do
     code=$(curl -s -o /dev/null -w '%{http_code}' -H "x-goog-api-key: $GEMINI_API_KEY" -H 'Content-Type: application/json' \
       -d '{"contents":[{"parts":[{"text":"Say OK"}]}]}' \
       "https://generativelanguage.googleapis.com/v1/models/$m:generateContent")
     echo "$m -> $code"
   done
   ```

   Expected: `200` for a working model. `404` means retired: pick another name from
   `curl -s -H "x-goog-api-key: $GEMINI_API_KEY" "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200" | grep -o '"name": "models/[^"]*"'`
   and test it the same way. Set the working name in `GEMINI_RESUME_MODEL` and `GEMINI_COVER_LETTER_MODEL`.
   `429` means the free-tier limit (wait a minute); `400/403` means a key problem.

To run without AI for now, set `RESUME_EXTRACTION_PROVIDER=local` and `COVER_LETTER_GENERATION_PROVIDER=local`
and leave `GEMINI_API_KEY` out (a placeholder key is still rejected).

---

## 8. Configure `.env`

**(server)** `cd /opt/jobslahfinder` first.

### 8.1 Generate domain, URL and secrets

```bash
DOMAIN=jobs.yourdomain.com EMAIL=you@yourmail.com bash infra/scripts/configure-env.sh
```

`EMAIL` is only used by Let's Encrypt for expiry notices (any address you can read). Optional off-server backups:
add `S3URI=s3://your-bucket/jobapp` (see [section 12.4](#124-optional-off-server-backups-to-s3)).

Expected output:

```
Generated POSTGRES_PASSWORD and DATABASE_URL.
Generated SESSION_SECRET.
Generated PASSWORD_RESET_SECRET.
Done. These settings still hold placeholders and need your real values (values hidden):
43:GEMINI_API_KEY=<hidden>
54:SMTP_HOST=<hidden>
56:SMTP_USERNAME=<hidden>
57:SMTP_PASSWORD=<hidden>
58:SMTP_FROM_EMAIL=<hidden>
```

The script is safe to re-run: secrets that are already set are never changed. It refuses to generate a new database
password if a Postgres volume already exists (that would lock the app out of its data).

### 8.2 Add the values only you have

```bash
nano .env
```

Set the five lines listed above (Brevo values from 7.1, Gemini key from 7.2). No quotes, no spaces around `=`.
Save with `Ctrl+O`, Enter, then exit with `Ctrl+X`. Leave `APP_ENV=production`, `DEBUG=false` and the
`COMPOSE_FILE` line alone.

### 8.3 Check it

```bash
grep -nE 'change-me|your-domain|example' .env | sed -E 's/=.*/=<hidden>/'
```

Expected: **no output**. Any line shown is a placeholder to replace. Then let the backend validate the settings:

```bash
docker compose run --rm --no-deps backend python -c "from app.core.config import get_settings; get_settings(); print('CONFIG OK')"
```

The first run builds the backend image (about 3 minutes, it installs Chromium). Expected last line: `CONFIG OK`.
A `ValueError` names the setting to fix. In production the backend refuses to start if: `FRONTEND_BASE_URL` is not
`https://` or points at localhost; any secret still contains a placeholder (`change-me`, `replace-with`, ...);
the session and reset secrets are identical or shorter than 32 characters; SMTP is not configured; or Gemini is
enabled without a key.

Do not paste `.env` contents anywhere. Do not commit it (it is git-ignored).

---

## 9. Get the HTTPS certificate

**(server)** Do a dry run against Let's Encrypt's **staging** server first. Failed real attempts are limited (5 per
hostname per hour); staging has no such limit.

```bash
cd /opt/jobslahfinder
LETSENCRYPT_STAGING=1 sh infra/scripts/init-letsencrypt.sh
```

Expected (shortened):

```
Creating temporary self-signed certificate so Nginx can start...
 ✔ Container jobslahfinder-nginx-1 Started
Requesting Let's Encrypt certificate for jobs.yourdomain.com...
Successfully received certificate.
...
Done. Test: curl -I https://jobs.yourdomain.com
```

Then discard the test certificate and get the real one:

```bash
sudo rm -rf infra/certbot/conf
sh infra/scripts/init-letsencrypt.sh
curl -sI https://jobs.yourdomain.com | head -3
echo | openssl s_client -connect jobs.yourdomain.com:443 -servername jobs.yourdomain.com 2>/dev/null | openssl x509 -noout -issuer -dates
```

Expected: `HTTP/2 200`, an `issuer=C = US, O = Let's Encrypt, CN = ...` line (not `STAGING` and not your own
domain name) and a `notAfter` about 90 days away. Renewal runs automatically from the root cron job.

If `issuer` equals your domain and `notAfter` is tomorrow, you are still on the temporary self-signed certificate:
see [Certificates](#certificates-and-the-browser).

---

## 10. Create the database and admin, start everything

**(server)**

```bash
cd /opt/jobslahfinder
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.cli create-initial-admin --email you@yourmail.com
docker compose up -d --build
docker compose ps
```

- `alembic upgrade head` prints a series of `Running upgrade ... -> 0009_merge_remaining_heads` lines and ends without error.
- `create-initial-admin` asks for a password twice (nothing is echoed) and prints `Initial admin created for you@yourmail.com.` Choose a long password and store it in a password manager. There is no default password.
- `docker compose ps` shows every service `Up` and `healthy` (nginx has no health status).

Run the automatic checks:

```bash
bash infra/scripts/verify-deploy.sh
```

Expected: 19 lines starting with `PASS` and `Result: 19 passed, 0 failed`:

```
PASS  DNS for jobs.yourdomain.com resolves to this VM (...)
PASS  .env permissions are 600
PASS  Backend config validates (no placeholder secrets)
PASS  All compose services running
PASS  No unhealthy containers
PASS  HTTP redirects to HTTPS (301)
PASS  HTTPS certificate is valid
PASS  HSTS header present
PASS  CSP header present
PASS  Backend /health returns 200
PASS  /api/me is 401 when logged out
PASS  API docs are not exposed (/docs is not 200)
PASS  Server version hidden
PASS  Uploads not web-accessible
PASS  Port 5432 closed on public IP
PASS  Port 6379 closed on public IP
PASS  Port 8000 closed on public IP
PASS  Backup directory is private (700)
PASS  Cron jobs installed
```

Any `FAIL` is explained in [Troubleshooting](#15-troubleshooting) (the HTTPS lines fail while a temporary certificate is installed).

---

## 11. First login and feature checks

1. Open `https://jobs.yourdomain.com` in a browser. You should see a padlock (if the page says "Not secure", fully close and reopen the browser once: see [Certificates](#certificates-and-the-browser)).
2. **Sign in** with the admin email and password. The first login only allows **two-factor setup**: scan the QR code with Microsoft Authenticator or Google Authenticator and enter the 6-digit code. Then sign in again if asked.
3. Open `/admin`: the dashboard loads and the health panel shows backend, database, Redis and worker as healthy.
4. **Risk-engine dashboard:** open `https://jobs.yourdomain.com/risk-engine/admin/dashboard` while signed in as admin. It lists recent logins with a score and a decision (`ALLOW`, `CHALLENGE`). Note: `/risk-engine/admin` and `/risk-engine/admin/login` only redirect to the normal sign-in page, and the dashboard needs a login less than 2 hours old.
5. **Password reset email:** sign out, **Reset password**, enter the admin email. The Brevo email arrives within a minute (check spam) and its link opens a "choose a new password" page on your domain.
6. **Scraping:** in `/admin`, trigger a scraping run, then open `/jobs`. Jobs from the approved sources appear.
7. **Normal user path:** register a second account (for example `you+test@yourmail.com`), set up its two-factor, upload a PDF resume (extraction completes; the extracted profile shows skills), generate recommendations, and generate a cover letter.
8. **Access control:** signed in as the normal user, `https://jobs.yourdomain.com/admin` must be denied or redirect away.
9. **Error pages:** `https://jobs.yourdomain.com/api/nonexistent` returns a short `{"detail":"Not Found"}` with no stack trace or file paths.
10. **Ports from outside:** from another machine (not the server, and use the **server's** IP, not your own), a port scanner such as https://www.yougetsignal.com/tools/open-ports/ must show 5432, 6379 and 8000 as closed or filtered. 80 and 443 are open; 22 is reachable only from your own IP.

The risk-engine API key (`curl -X POST https://jobs.yourdomain.com/risk-engine/setup`, shown once) is **not**
needed for any of the above. It only protects a separate machine-to-machine API. Skip it unless you use that API;
if you run it, store the returned key in a password manager immediately.

Optional GeoIP database for the impossible-travel check (the check is skipped without it):

```bash
MAXMIND_LICENSE_KEY=<your key> sh infra/scripts/download-geolite.sh
docker compose up -d backend
```

---

## 12. Backups and restore test

### 12.1 What is backed up

`infra/scripts/backup-prod.sh` writes a timestamped folder under `/var/backups/jobapp` containing the PostgreSQL
dump, the resume-storage and risk-engine volumes, and `SHA256SUMS`. The folder is root-only (mode 700) on purpose,
so **run it with `sudo`**. The nightly cron job (02:30) already runs as root. Backups older than
`BACKUP_RETENTION_DAYS` (default 14) are removed.

### 12.2 Run one and test the restore

**(server)**

```bash
cd /opt/jobslahfinder
sudo bash infra/scripts/backup-prod.sh
NEWEST=$(sudo ls -1 /var/backups/jobapp | tail -1)
sudo bash infra/scripts/restore-test.sh /var/backups/jobapp/$NEWEST
```

Expected from the restore test (it restores into a throwaway container and never touches production):

```
/var/backups/jobapp/2026....Z/postgres.dump: OK
/var/backups/jobapp/2026....Z/resume_storage.tar.gz: OK
/var/backups/jobapp/2026....Z/risk_engine_data.tar.gz: OK
Restore OK: 16 public tables, 2 users.
```

For encrypted backups the file names end in `.gpg` and the test needs the passphrase (see 12.3). `<newest-folder>` in
older notes is a placeholder: the `NEWEST=` line fills it in.

### 12.3 Encrypt the backups (recommended)

Backups contain user data and resume files. Encrypt them with a passphrase that lives only on the server and in
your password manager (never in git, S3 or chat).

```bash
sudo mkdir -p /etc/jobapp && sudo chmod 700 /etc/jobapp
sudo sh -c 'umask 077; openssl rand -base64 32 > /etc/jobapp/backup-passphrase'
sudo cat /etc/jobapp/backup-passphrase          # copy it into your password manager NOW
echo 'BACKUP_PASSPHRASE_FILE=/etc/jobapp/backup-passphrase' >> .env
sudo bash infra/scripts/backup-prod.sh
```

Without that passphrase an encrypted backup **cannot** be restored, so store a copy somewhere that survives the
server. Encrypted backups contain `postgres.dump.gpg`, `resume_storage.tar.gz.gpg` and
`risk_engine_data.tar.gz.gpg` (plus `SHA256SUMS`). Backups made before you turned encryption on stay plaintext until
they expire. `restore-test.sh` does not read `.env`, so pass the passphrase file explicitly:

```bash
NEWEST=$(sudo ls -1 /var/backups/jobapp | tail -1)
sudo BACKUP_PASSPHRASE_FILE=/etc/jobapp/backup-passphrase bash infra/scripts/restore-test.sh /var/backups/jobapp/$NEWEST
```

Other optional settings in `.env`: `BACKUP_RETENTION_DAYS` (default 14).

### 12.4 Optional: off-server backups to S3

Without this, backups only protect against mistakes, not against losing the whole server.

1. https://console.aws.amazon.com/s3 (Singapore) -> **Create bucket**: a globally unique lower-case name, **Block all public access ON**, **Bucket Versioning: Enable**, default encryption on.
2. IAM -> Policies -> Create policy -> JSON (replace `YOUR-BUCKET-NAME`), name `jobapp-backup-upload`, and attach it to `jobapp-ec2-role` (from 4.2). The server can add files but not read or delete them, so a compromised server cannot wipe the backups:

   ```json
   {"Version":"2012-10-17","Statement":[
    {"Effect":"Allow","Action":["s3:PutObject"],"Resource":"arn:aws:s3:::YOUR-BUCKET-NAME/jobapp/*"},
    {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::YOUR-BUCKET-NAME","Condition":{"StringLike":{"s3:prefix":["jobapp/*"]}}}]}
   ```
3. Recommended bucket settings: **Versioning on**, and a **lifecycle rule** (Management -> Create lifecycle rule, prefix `jobapp/`) that expires current versions after 30 days and permanently deletes noncurrent versions after 7 days, plus "delete incomplete multipart uploads" after 7 days. The instance role cannot delete or read objects, so this rule is the only S3 pruning, and **restoring from S3 needs different credentials** (for example your own admin user) or a temporary read policy.
4. **Check the bucket really exists before using it:**

   ```bash
   curl -sI https://YOUR-BUCKET-NAME.s3.amazonaws.com | head -1
   ```

   `404 Not Found` means no such bucket (a typo, or a policy name used instead of the bucket name). `403` or `301` means it exists.
5. In `.env` set `BACKUP_S3_URI=s3://YOUR-BUCKET-NAME/jobapp`, then:

   ```bash
   sudo bash infra/scripts/backup-prod.sh
   aws s3 ls s3://YOUR-BUCKET-NAME/jobapp/
   ```

   Expected: the backup ends with `Backup complete` and `aws s3 ls` lists a `2026....Z/` folder.

If you do not use S3, keep `BACKUP_S3_URI` unset or commented out (`# BACKUP_S3_URI=...`): a set but broken value makes
every nightly backup fail at the upload step before the old-backup cleanup runs.

---

## 13. Automatic deploys from GitHub (AWS Systems Manager)

The deploy job does **not** use SSH, so port 22 stays restricted to your own IP. GitHub assumes a short-lived AWS
role through OpenID Connect (no long-lived AWS keys), then tells the instance, through Systems Manager (SSM), to
run `infra/scripts/deploy.sh` as the `ubuntu` user. `deploy.sh` takes a pre-deploy backup, checks out the commit,
builds, runs `alembic upgrade head`, restarts, smoke-tests `https://$DOMAIN/health` and **rolls the code back
automatically** if the smoke test fails. (Migrations are not reverted: restore the pre-deploy backup if a schema
change must be undone.)

### 13.1 One-time AWS setup (console, Singapore)

1. **Let the instance accept SSM commands.** The instance role from 4.2 needs **AmazonSSMManagedInstanceCore** and must be attached to the instance. After a few minutes the instance shows as **Online** under Systems Manager -> **Fleet Manager** (Ubuntu 24.04 AWS images include the SSM agent). Note the **instance ID** (`i-...`) and your **AWS account ID** (top-right menu).
2. **Create the GitHub identity provider** (once per account): IAM -> Identity providers -> Add provider -> OpenID Connect -> Provider URL `https://token.actions.githubusercontent.com`, Audience `sts.amazonaws.com`.
3. **Create the deploy role:** IAM -> Roles -> Create role -> **Web identity** -> provider `token.actions.githubusercontent.com`, audience `sts.amazonaws.com` -> skip permissions -> name `github-deploy-jobslahfinder`. Open the role -> **Trust relationships -> Edit trust policy** (replace `ACCOUNT_ID`; keep the capitalisation of your GitHub owner and repository exactly):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": { "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com" },
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringEquals": {
           "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
           "token.actions.githubusercontent.com:sub": "<EXACT SUBJECT, see below>"
         }
       }
     }]
   }
   ```

   The subject ends in `:environment:production` because the deploy job declares `environment: production`. **The
   part before it depends on your repository**, and GitHub may include numeric IDs. Two forms exist:

   | Form | Example |
   | --- | --- |
   | Default | `repo:OWNER/REPO:environment:production` |
   | With IDs (newer or customised repositories) | `repo:OWNER@OWNER_ID/REPO@REPO_ID:environment:production` |

   Do not guess: use the value GitHub really sends. The reliable way is to run the deploy once (it will be refused),
   then open **CloudTrail -> Event history**, filter on Event name `AssumeRoleWithWebIdentity`, open the failed event
   and copy the **User name** field. That string is the exact subject; paste it into the trust policy, save, and run
   the workflow again. (The subject setting itself can be read with
   `gh api repos/OWNER/REPO/actions/oidc/customization/sub` if you use the GitHub CLI.) Keep the capitalisation exactly as shown.
4. **Give the role only what it needs:** Role -> Add permissions -> Create inline policy -> JSON (replace `ACCOUNT_ID` and `INSTANCE_ID`):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "ssm:SendCommand",
         "Resource": [
           "arn:aws:ssm:ap-southeast-1::document/AWS-RunShellScript",
           "arn:aws:ec2:ap-southeast-1:ACCOUNT_ID:instance/INSTANCE_ID"
         ]
       },
       {
         "Effect": "Allow",
         "Action": ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"],
         "Resource": "*"
       }
     ]
   }
   ```
5. Copy the role's **ARN** (`arn:aws:iam::ACCOUNT_ID:role/github-deploy-jobslahfinder`).

### 13.2 GitHub settings

Repository -> Settings -> Secrets and variables -> Actions -> **Secrets**
(https://github.com/Ryan-wong123/Jobslahfinder/settings/secrets/actions):

| Secret | Value |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | the role ARN from 13.1 step 5 |
| `EC2_INSTANCE_ID` | the `i-...` instance ID |
| `DEPLOY_PATH` | `/opt/jobslahfinder` |

Optional repository **variable** `AWS_REGION` (defaults to `ap-southeast-1`). The old `EC2_HOST`, `EC2_USER`,
`EC2_PORT` and `EC2_SSH_KEY` secrets are no longer used and can be deleted.

### 13.3 Test deploy

GitHub -> Actions -> **CI/CD** -> **Run workflow** -> branch `production` (or `main`) -> Run. Always start a **new**
run after changing code: "Re-run failed jobs" reuses the old commit. Expected in the **Deploy To EC2** log:

```
Authenticated as assumedRoleId ...:github-deploy
Sending deploy command for <40-char sha> to *** via SSM...
SSM command id: <uuid>
[15 s] status: InProgress
...
[xxx s] status: Success
Deploy succeeded.
```

A full deploy takes a few minutes (it builds images). Afterwards on the server `git log -1 --oneline` shows the
deployed commit, a new folder exists in `/var/backups/jobapp`, and `bash infra/scripts/verify-deploy.sh` still
passes 19/19.

### 13.4 Lock it down

- Settings -> Environments -> `production` -> Deployment branches and tags -> **Selected branches: `main`**, so only `main` can use the role (do this after testing from another branch).
- Optional: Required reviewers on the `production` environment for a manual approval step; protect `main` (require a pull request and passing checks).
- From then on every merge or push to `main` runs the full CI and then deploys. The deploy job only runs after backend, migration, frontend, security and Docker checks pass.

---

## 14. Day-to-day operations

| Task | Command (server, in `/opt/jobslahfinder`) |
| --- | --- |
| Status of all services | `docker compose ps` |
| Logs | `docker compose logs --tail=80 backend` (also `worker`, `nginx`, `frontend`, `beat`) |
| Restart backend and worker | `docker compose up -d backend worker` |
| Manual deploy of a commit | `DEPLOY_SHA=$(git rev-parse origin/main) bash infra/scripts/deploy.sh` (run `git fetch origin` first) |
| Take a backup now | `sudo bash infra/scripts/backup-prod.sh` |
| Check the health checks | `bash infra/scripts/verify-deploy.sh` |
| Test certificate renewal | `docker compose run --rm certbot renew --dry-run` |
| See the root cron jobs | `sudo crontab -l` |
| Backup/renewal logs | `sudo tail /var/log/jobapp-backup.log /var/log/jobapp-cert-renew.log` |

- **Your IP changed** (new network, hotspot): SSH stops working. Edit the security group's SSH rule (EC2 -> instance -> Security -> the group -> Edit inbound rules) and set the source to **My IP** again.
- **Resume extraction suddenly fails** with `parser_failed` and the worker log shows `404 Not Found` from `generativelanguage.googleapis.com`: the Gemini model was retired. Re-run the model test in 7.2 and update `GEMINI_RESUME_MODEL` and `GEMINI_COVER_LETTER_MODEL` in `.env`, then `docker compose up -d backend worker`.
- **Never re-generate secrets** once the database exists. `configure-env.sh` already protects the database password; do not edit `POSTGRES_PASSWORD` by hand.
- **Scheduled jobs:** weekly scraping runs Sundays 18:00 UTC (Celery beat). Check `/admin` -> scraping runs.
- **Updating the risk-engine key or other secrets:** edit `.env` on the server, then `docker compose up -d`.

---

## 15. Troubleshooting

Find your symptom. Each entry says what it means and how to fix it.

### SSH and your PC

| Symptom | Cause and fix |
| --- | --- |
| `Warning: Identity file ... not accessible: No such file or directory` then `Permission denied (publickey)` | SSH never found the key, so it offered none. You are in the wrong folder or the file has another name (`jobslahfinder-key (1).pem`, `.pem.txt`). Find it: `Get-ChildItem -Path $HOME -Filter "jobslahfinder-key*" -Recurse -ErrorAction SilentlyContinue \| Select FullName`, then use the full path with `-i`. |
| `Bad permissions ... UNPROTECTED PRIVATE KEY FILE` (may name another account, e.g. a sandbox user group) | Windows inheritance gives other accounts read access. Run the three `icacls` commands in [section 5](#5-connect-with-ssh). If it still fails, copy the key to `$HOME\.ssh\` and apply `icacls` to the copy. |
| Key file lost | A key cannot be recovered. Create a new key pair, terminate the (empty) instance, launch a new one with the new key, re-associate the Elastic IP. Once the SSM deploy is set up you can also use Systems Manager Session Manager. |
| `cd : Cannot find path 'C:\opt\jobslahfinder'`, `sed`/`grep` "not recognized" | You ran **server** commands in your **PC's** PowerShell. Run `ssh ...` first; the prompt must read `ubuntu@ip-172-31-...`. `exit` returns you to the PC. |
| SSH hangs or times out | Your IP changed or the security group SSH rule is wrong: set the source to **My IP** again. |
| Port-check results look wrong | The scanner must target the **server's** IP, not your own (the tool's "Use Current IP" button fills in your own IP). `nmap` run **on** the server tests the server against itself and is not a valid external check. |
| AWS "You have not made any changes" or the `0.0.0.0/0` warning when editing the security group | Both are informational: the rules were already correct, and `0.0.0.0/0` on 80/443 is intended. Click Cancel. |

### Certificates and the browser

| Symptom | Cause and fix |
| --- | --- |
| Certbot: `Connection refused` fetching `/.well-known/acme-challenge/...` | Nothing was listening on port 80: either Nginx was down (check `docker compose ps` and `docker compose logs --tail=40 nginx`) or port 80 is closed in the security group. An older version of `init-letsencrypt.sh` could leave Nginx crash-looping with `cannot load certificate ...fullchain.pem`; update the repo (`git pull`) and re-run. |
| Script prints `Nginx is not answering on port 80` while the logs show requests | Old script versions probed `127.0.0.1` without a hostname, which Nginx deliberately drops (status 444). Update the repo; the probe now sends your domain. |
| Certbot `too many failed authorizations` | Let's Encrypt allows 5 failures per hostname per hour. Fix the cause, wait an hour, and use `LETSENCRYPT_STAGING=1` while testing. |
| `curl -I https://...` works only with `-k`, or `issuer` equals your domain and `notAfter` is tomorrow | You still have the temporary self-signed certificate (a `.dummy` file exists in `infra/certbot/conf/live/<domain>/`). Run section 9 again. |
| `verify-deploy.sh` fails the HTTPS, HSTS, CSP, `/health` and `/api/me` lines only | Same cause: a temporary or staging certificate. |
| Browser says "Not secure" although "Certificate is valid" | The tab or browser remembers an earlier certificate warning you clicked through. Fully close every browser window (check the system tray), reopen, and type the `https://` address yourself. Or open a private window or another browser. |
| `ls infra/certbot/conf` or `rm` needs `sudo` | The certbot container writes as root. Use `sudo rm -rf infra/certbot/conf` before re-running the staging-to-real switch. |

### `.env` and backend start-up

| Symptom | Cause and fix |
| --- | --- |
| Backend exits with `ValueError: ... placeholder ...` | A secret or key still contains `change-me`, `replace-with` and similar. Run `grep -nE 'change-me\|your-domain\|example' .env \| sed -E 's/=.*/=<hidden>/'` and fix each listed setting. |
| `FRONTEND_BASE_URL must use https in production` | Set `FRONTEND_BASE_URL=https://<your domain>`; `configure-env.sh` does this. |
| `SESSION_SECRET and PASSWORD_RESET_SECRET must be different` or `at least 32 characters` | Re-run `configure-env.sh` with the placeholders cleared, or generate separate values with `openssl rand -base64 48`. |
| Database "password authentication failed" after editing `.env` | Postgres sets its password only when its volume is first created. Restore the original `POSTGRES_PASSWORD` in `.env`. Only if the database holds nothing you need: `docker compose down -v` and start again (this deletes data). |
| `configure-env.sh` says a Postgres volume already exists | Intentional protection (see above). Do not force it unless the database can be recreated. |

### Login, admin and risk engine

| Symptom | Cause and fix |
| --- | --- |
| "Invalid request" when you paste the risk-engine key into the sign-in form | That form takes your **email and password** only. The key is not a login. |
| `/risk-engine/admin/login` or `/risk-engine/admin` redirects to the sign-in page, then to `/admin` (a loop) | Those two URLs only redirect. The dashboard is at `/risk-engine/admin/dashboard`. |
| Dashboard says authentication or two-factor is required | Your admin login is more than 2 hours old (`ADMIN_SESSION_MAX_AGE_MINUTES`), or two-factor is not set up for the admin account. Sign out, sign in, open the dashboard right away. |
| First login only shows a two-factor page | Expected: new accounts must enrol an authenticator app before getting a full session. |
| Password-reset email never arrives | Check spam; confirm the sender is verified in Brevo (unverified senders are dropped silently) and `SMTP_USERNAME` is the Brevo SMTP login, not your email; read `docker compose logs --tail=40 backend`. |

### Resume extraction and AI

| Symptom | Cause and fix |
| --- | --- |
| Resume status shows failed | Run `docker compose exec -T postgres psql -U jobapp -d jobapp -c "select id, outcome, details_json from audit_logs where event_type='resume.extraction' order by id desc limit 5;"`. `parser_failed` with a Gemini `404 Not Found` in `docker compose logs --tail=60 worker` means the model was retired: see 7.2. `ai_provider_auth_failed` means a bad key; `ai_provider_rate_limited` means free-tier limits; `parser_failed` with no Gemini 404 means the file could not be read (try a text-based PDF, not a scan). |
| Cover letters work but look generic | The app silently falls back to a template when Gemini fails. Fix the Gemini problem above; letters then come from the model. |
| The model appears in the model list but returns 404 | Retired. Listing is not proof: test with `generateContent` as in 7.2. |

### Backups

| Symptom | Cause and fix |
| --- | --- |
| `mkdir: cannot create directory '/var/backups/jobapp': Permission denied` | The folder is root-only by design. Use `sudo bash infra/scripts/backup-prod.sh`. |
| `-bash: syntax error near unexpected token 'newline'` after `restore-test.sh ... <newest-folder>` | `<newest-folder>` is a placeholder, not literal text. Use the `NEWEST=$(sudo ls -1 /var/backups/jobapp \| tail -1)` line from 12.2. |
| `upload failed ... NoSuchBucket` | The bucket name in `BACKUP_S3_URI` does not exist (check with the `curl -sI` test in 12.4; often a policy name was used or the bucket was never created). Create the bucket, or comment the setting out. |
| `AccessDenied` on upload | The bucket exists but the instance role lacks the policy (12.4 step 2) or the policy names a different bucket. |
| Nightly backup keeps the disk filling up | A failing upload aborts the script before the old-backup cleanup. Fix or disable S3 as above. |

### Automatic deploys (GitHub Actions)

| Symptom | Cause and fix |
| --- | --- |
| All jobs fail in about two seconds with no log | A GitHub account problem (Actions spending limit or minutes, billing) rather than the code: check Settings -> Billing and Actions. |
| `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity` | The role's trust policy does not match what GitHub sent. Most often the **`sub` form is wrong**: some repositories send numeric IDs (`repo:OWNER@OWNER_ID/REPO@REPO_ID:environment:production`) instead of `repo:OWNER/REPO:environment:production`. Read the exact subject from CloudTrail (Event history -> `AssumeRoleWithWebIdentity` -> **User name**) and paste it into the trust policy. Also check: the subject is not `ref:refs/heads/main` or an old repository name; `aud` is `sts.amazonaws.com`; the `Principal` has your real account ID; the OIDC provider exists; `AWS_DEPLOY_ROLE_ARN` points at this role. |
| `AccessDeniedException ... ssm:SendCommand` | The inline policy has a wrong account ID, instance ID or region in its ARNs. |
| `InvalidInstanceId` / the command never starts | The instance is not **Online** in Fleet Manager: the instance role lacks `AmazonSSMManagedInstanceCore` or is not attached, or the SSM agent is not running (`sudo snap list amazon-ssm-agent`). |
| Remote error `set: Illegal option -o pipefail` | SSM runs command lines with `sh` (dash), which has no `pipefail`. Fixed in `infra/scripts/ssm-deploy.sh` (POSIX wrapper; the real script runs under `bash`). Make sure you are running a commit that includes the fix, and start a **new** workflow run. |
| Status `Failed` with "Rolling back" in the output | The new commit failed the `/health` smoke test; the code was rolled back automatically. Read the remote output, fix, redeploy. Migrations are not reverted. |
| Permission denied on `/var/backups/jobapp` inside the deploy | `deploy.sh` runs the backup with `sudo`; check the `ubuntu` user has passwordless sudo (`sudo -n true`). |
| Re-running a failed job does not pick up your fix | "Re-run failed jobs" reuses the old commit. Use **Run workflow** for a new run on the branch. |
| Security Checks fail on `npm audit` | A dependency vulnerability. Run `npm audit fix` in `frontend/`, then lint, typecheck, tests and build, and commit `package-lock.json`. |
| `test_resume_extraction_success_and_failure_do_not_log_full_resume_text` fails in CI | The test raced the 10-second parser timeout on a slow runner (the audit showed `parser_timeout`). The test now uses a longer timeout. |
| Deploy cannot connect over SSH | The deploy no longer uses SSH. Keep port 22 restricted to your IP. |

### Server

| Symptom | Cause and fix |
| --- | --- |
| Nginx container keeps restarting | `docker compose logs --tail=40 nginx`. `cannot load certificate` means the certificate files are missing: re-run section 9. A config error names the line. |
| Disk filling up | `docker system df`, then `docker image prune -f`; logs are rotated (10 MB x 5 per container); old backups are cleaned by the backup script. |
| After a reboot something is down | All services use `restart: unless-stopped`; run `docker compose up -d`. |

---

## 16. Reference

### Scripts (`infra/scripts/`)

| Script | Purpose | Run as |
| --- | --- | --- |
| `bootstrap-vm.sh` | One-time server setup (Docker, AWS CLI, cron jobs, `.env` template) | `ubuntu` |
| `configure-env.sh` | Fill `.env` with domain, URL and random secrets (idempotent, protects the DB password) | `ubuntu` |
| `init-letsencrypt.sh` | Issue the HTTPS certificate (`LETSENCRYPT_STAGING=1` for a dry run) | `ubuntu` |
| `renew-certs.sh` | Renew certificates and reload Nginx (cron, twice daily) | root (cron) |
| `verify-deploy.sh` | 19 post-deploy checks | `ubuntu` |
| `backup-prod.sh` | Backup (Postgres, volumes; optional encryption and S3) | `sudo` / root |
| `restore-test.sh <folder>` | Verify a backup restores into a throwaway database | `sudo` |
| `deploy.sh` | Backup, checkout, build, migrate, restart, smoke test, rollback | `ubuntu` |
| `ssm-deploy.sh` | CI helper: runs `deploy.sh` on the instance through SSM | GitHub Actions |
| `download-geolite.sh` | Optional MaxMind GeoLite2 download | `ubuntu` |

### `.env` settings you edit (names only, no values here)

`DOMAIN`, `FRONTEND_BASE_URL`, `LETSENCRYPT_EMAIL`, `COMPOSE_FILE` (set by `configure-env.sh`);
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `SESSION_SECRET`, `PASSWORD_RESET_SECRET`
(generated); `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`;
`GEMINI_API_KEY`, `GEMINI_RESUME_MODEL`, `GEMINI_COVER_LETTER_MODEL`, `RESUME_EXTRACTION_PROVIDER`,
`COVER_LETTER_GENERATION_PROVIDER`; `BACKUP_S3_URI`, `BACKUP_RETENTION_DAYS`, `BACKUP_PASSPHRASE_FILE`,
`BACKUP_DIR`; `MAXMIND_LICENSE_KEY` (only for the download script). `.env.example` lists every name with a
placeholder; the real `.env` is never committed.

### Network and security summary

- Public: 80 (redirects to HTTPS) and 443. SSH: your IP only. PostgreSQL, Redis and the backend are never published.
- Nginx adds HSTS, CSP, frame/referrer/permissions policies, rate limits on `/api/auth/*` and `/api/*`, a 5 MB upload limit, and drops requests for unknown hostnames.
- Accepted risk: the CSP allows `'unsafe-inline'` for scripts (needed by Next.js hydration). See `docs/security-hardening.md`.
- Resume files are stored in a Docker volume, never in a web root; the backup folder is root-only.

### Self-signed HTTPS for an IP-only demo (not for production)

```bash
sh ./infra/scripts/create-ec2-self-signed-cert.sh <EC2_PUBLIC_IP>
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build
```

Browsers will warn about the certificate. Do not use this for a public site.

### Related documents

`TASK.md` (checklist for finishing and verifying the deployment, for a local assistant session),
`docs/security-hardening.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`, `README.md`.
