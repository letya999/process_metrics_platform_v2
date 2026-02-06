# Digital Ocean Deployment Guide

This guide covers deploying Process Metrics Platform to Digital Ocean.

## Deployment Options

| Option | Pros | Cons | Recommended For |
|--------|------|------|-----------------|
| **Droplet + Docker** | Full control, cost-effective | Manual maintenance | Production, small teams |
| **App Platform** | Managed, auto-scaling | Higher cost | Enterprise, larger teams |
| **Kubernetes (DOKS)** | Scalable, standard K8s | Complex setup | Large scale deployments |

**Recommendation:** Start with **Droplet + Docker Compose** for MVP.

---

## Option 1: Droplet + Docker Compose (Recommended)

### Prerequisites

- Digital Ocean account
- SSH key configured
- Domain name (optional but recommended)

### Step 1: Create Droplet

1. Go to [Digital Ocean Dashboard](https://cloud.digitalocean.com/)
2. Create → Droplets
3. Choose:
   - **Image:** Ubuntu 22.04 LTS
   - **Plan:** Basic → Regular → $24/mo (4GB RAM, 2 vCPUs) minimum
   - **Region:** Choose closest to your team
   - **Auth:** SSH Key (recommended)
4. Create Droplet

### Step 2: Initial Server Setup

SSH into your droplet:

```bash
ssh root@YOUR_DROPLET_IP
```

Install Docker:

```bash
# Update packages
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

Create a deploy user (optional but recommended):

```bash
adduser deploy
usermod -aG docker deploy
usermod -aG sudo deploy

# Copy SSH key
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
```

### Step 3: Clone Repository

```bash
# As deploy user
su - deploy
cd ~

# Clone repo (or upload files)
git clone https://github.com/your-org/process_metrics_platform.git
cd process_metrics_platform
```

### Step 4: Configure Environment

```bash
# Copy example files
cp .env.production.example .env.production
cp config/projects.example.yaml config/projects.yaml

# Edit production environment
nano .env.production
```

Generate secure passwords:

```bash
# Generate strong password
openssl rand -base64 32

# Generate secret key
openssl rand -hex 32
```

Example `.env.production`:

```bash
POSTGRES_DB=process_metrics
POSTGRES_USER=metrics_app
POSTGRES_PASSWORD=<YOUR_GENERATED_PASSWORD>

JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_USER_EMAIL=admin@company.com
JIRA_API_TOKEN=<YOUR_JIRA_TOKEN>

SECRET_KEY=<YOUR_GENERATED_SECRET>
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

Edit projects config:

```bash
nano config/projects.yaml
```

### Step 5: Deploy

```bash
# Make deploy script executable
chmod +x scripts/deploy.sh

# Deploy
./scripts/deploy.sh --build

# OR use docker compose directly:
docker compose -f docker-compose.prod.yml up -d
```

### Step 6: Run Migrations

```bash
docker compose -f docker-compose.prod.yml exec app \
  alembic -c db/migrations/alembic.ini upgrade head
```

### Step 7: Verify Deployment

```bash
# Check services
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Test health endpoints
curl http://localhost:8000/health
curl http://localhost:3000/server_info
```

---

## Setting Up HTTPS (Recommended)

### Option A: Caddy Reverse Proxy (Easiest)

Create `Caddyfile`:

```caddy
metrics.yourdomain.com {
    reverse_proxy app:8000
}

dagster.yourdomain.com {
    reverse_proxy dagster:3000
}

metabase.yourdomain.com {
    reverse_proxy metabase:3000
}
```

Add to `docker-compose.prod.yml`:

```yaml
services:
  caddy:
    image: caddy:latest
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    networks:
      - process_metrics_network

volumes:
  caddy_data:
```

### Option B: Digital Ocean Load Balancer

1. Create Load Balancer in DO Dashboard
2. Add HTTPS listener with Let's Encrypt
3. Forward to Droplet on internal ports

---

## Using DO Managed Database (Optional)

For production, consider using Digital Ocean Managed PostgreSQL:

1. Create Database Cluster (PostgreSQL 15)
2. Get connection details
3. Update `.env.production`:

```bash
DATABASE_URL=postgresql://doadmin:<PASSWORD>@<HOST>:25060/process_metrics?sslmode=require
```

4. Remove postgres service from docker-compose.prod.yml

Benefits:
- Automatic backups
- High availability
- Managed updates

---

## Firewall Configuration

```bash
# Allow SSH
ufw allow 22

# Allow HTTP/HTTPS (if using reverse proxy)
ufw allow 80
ufw allow 443

# OR allow direct ports (if no reverse proxy)
ufw allow 8000
ufw allow 3000
ufw allow 3001

# Enable firewall
ufw enable
```

---

## Monitoring and Maintenance

### View Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f dagster
```

### Restart Services

```bash
docker compose -f docker-compose.prod.yml restart
```

### Update Deployment

```bash
cd ~/process_metrics_platform
git pull
./scripts/deploy.sh --build
```

### Backup Database

```bash
# Create backup
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U metrics_app process_metrics > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20240101.sql | docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U metrics_app process_metrics
```

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs app

# Check container status
docker compose -f docker-compose.prod.yml ps -a
```

### Database connection issues

```bash
# Test connection
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U metrics_app -d process_metrics -c "SELECT 1"
```

### Memory issues

```bash
# Check memory usage
docker stats

# Increase swap if needed
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

---

## Cost Estimation

| Resource | Monthly Cost |
|----------|--------------|
| Droplet (4GB) | $24 |
| Managed DB (optional) | $15+ |
| Load Balancer (optional) | $12 |
| **Total (minimal)** | **$24** |
| **Total (full)** | **$51+** |
