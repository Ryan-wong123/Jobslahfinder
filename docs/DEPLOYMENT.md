# EC2 CI/CD Deployment

This repository deploys through GitHub Actions in `.github/workflows/ci-cd.yml`.

The pipeline runs backend tests, frontend lint/typecheck/build, security checks, Docker build validation, and then deploys to EC2 over SSH after successful checks.

## GitHub Secrets

Create these repository secrets in GitHub:

GitHub path: `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`.

| Secret | Example | Notes |
| --- | --- | --- |
| `EC2_HOST` | `13.250.10.20` | Public IPv4 or DNS name of the EC2 instance. |
| `EC2_USER` | `ubuntu` | SSH user for the instance. Amazon Linux often uses `ec2-user`. |
| `EC2_PORT` | `22` | Optional. Defaults to `22` if omitted. |
| `EC2_SSH_KEY` | Private key contents | The private key that can SSH into the EC2 instance. |
| `DEPLOY_PATH` | `/opt/jobslahfinder` | Absolute path to the checked-out repository on EC2. |

Never commit SSH keys, `.env`, generated secrets, backups, logs, or uploaded files.

For `EC2_SSH_KEY`, paste the full private key including the begin/end lines, for example:

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

Do not store this private key on EC2 for GitHub Actions. EC2 should only have the matching public key in the deploy user's `~/.ssh/authorized_keys`.

## EC2 Setup

Install Git, Docker, and Docker Compose on the EC2 instance. Then clone the repo into the deployment path:

```bash
sudo mkdir -p /opt/jobslahfinder
sudo chown "$USER:$USER" /opt/jobslahfinder
git clone git@github.com:<owner>/<repo>.git /opt/jobslahfinder
cd /opt/jobslahfinder
```

The EC2 deploy user must be able to run Docker commands. Commonly this means adding the user to the `docker` group and starting a new login session.

The repository on EC2 must also be able to run `git fetch origin` during deployment. For private GitHub repositories, add a read-only GitHub deploy key or use another secure Git credential on the EC2 instance.

Create the production environment file on EC2:

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and replace every placeholder with production values. Use long random values for `POSTGRES_PASSWORD`, `SESSION_SECRET`, and `PASSWORD_RESET_SECRET`.

The EC2 security group should expose only the ports needed for this deployment:

- `22` for SSH, restricted to trusted IPs where possible.
- `80` and later `443` for web traffic.

PostgreSQL and Redis are internal Docker services and must not be exposed publicly.

## First Deployment

Push to `main` or run the `CI/CD` workflow manually from GitHub Actions.

The deploy job connects to EC2, checks out the exact commit, builds Docker images, runs Alembic migrations, and starts services:

```bash
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up -d --remove-orphans
```

After deployment, verify:

```bash
cd /opt/jobslahfinder
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 nginx
```

The current Compose file maps Nginx to host port `8080`. For public HTTP on port `80`, update `docker-compose.yml` to map `80:80` before production release, or route traffic through a host-level reverse proxy.
