# Deployment Commands

Short command reference for deploying the app on the Ubuntu EC2 instance.

## EC2 Project Directory

```bash
cd /home/student4/ssd-project
```

## First-Time Server Setup

Install Docker, Docker Compose, and Git:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

Log out of PuTTY and log back in, then check:

```bash
docker --version
docker compose version
```

## Clone The Repository

```bash
mkdir -p /home/student4/ssd-project
cd /home/student4/ssd-project
git clone https://github.com/Ryan-wong123/ICT2216_P1_Group4_Jobslahfinder.git .
```

For a private repo, use your GitHub username and a classic personal access token as the password.

## Create The EC2 `.env`

```bash
cd /home/student4/ssd-project
cp .env.example .env
nano .env
```

Minimum EC2 values to check:

```env
APP_ENV=production
DEBUG=false
API_HOST=0.0.0.0
NEXT_PUBLIC_API_BASE_URL=/api
FRONTEND_BASE_URL=https://jobs.your-domain.example
DOMAIN=jobs.your-domain.example
```

Do not commit `.env`.

## Deploy With HTTPS Ports 80/443

```bash
cd /home/student4/ssd-project
git fetch --prune origin
git checkout main
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build --force-recreate --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml exec -T backend alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml ps
```

## Normal Start After Restart

Use this when the EC2 instance was stopped/restarted, or when you just want to host the existing deployed code again.

```bash
cd /home/student4/ssd-project
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml ps
```

If containers do not start correctly, rebuild and recreate them:

```bash
cd /home/student4/ssd-project
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build --force-recreate --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml ps
```

If the backend starts but database tables are missing or outdated, run migrations:

```bash
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml exec -T backend alembic upgrade head
```

Visit:

```text
http://YOUR_EC2_PUBLIC_IP
```

It should redirect to:

```text
https://YOUR_EC2_PUBLIC_IP
```

## Logs

```bash
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml logs --tail=100 nginx
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml logs --tail=100 frontend
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml logs --tail=100 backend
```

## GitHub Actions Deploy Command

Use this inside the SSH deploy step:

```bash
cd /home/student4/ssd-project

git fetch --prune origin
git checkout --force "$DEPLOY_SHA"

docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build --force-recreate --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml exec -T backend alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml ps
```

## AWS Security Group

Allow inbound:

```text
22   SSH    your IP only if possible
80   HTTP   0.0.0.0/0
443  HTTPS  0.0.0.0/0
```

Do not expose:

```text
5432 PostgreSQL
6379 Redis
8080 old HTTP port
8443 old HTTPS port
```

## Notes

Using an EC2 IP with the local/self-signed certificate will show a browser certificate warning. For trusted HTTPS, use a domain name and a valid certificate such as Let's Encrypt.
