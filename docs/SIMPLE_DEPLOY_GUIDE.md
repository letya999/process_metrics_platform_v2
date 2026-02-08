# 🚀 Простой Self-Hosted Deploy на DigitalOcean

**Цель:** Развернуть Process Metrics Platform на одном droplet без платных сервисов и сложных enterprise-решений, но с базовой безопасностью.

**Время:** ~30-60 минут

---

## 📋 Что игнорируем из полного аудита

Полный аудит предлагает enterprise-решения. Для простого self-hosted деплоя **не нужны**:

| Из аудита | Почему не нужно |
|-----------|-----------------|
| Kubernetes | Overkill для 1 droplet |
| Redis кластер | Для 1-5 пользователей не критично |
| PostgreSQL replicas | Для self-hosted не нужно |
| HashiCorp Vault | Fernet шифрование достаточно |
| PagerDuty/Slack alerts | Email/Telegram проще |
| WAF | Cloudflare бесплатный справится |
| JWT + RBAC | Basic Auth + IP whitelist достаточно |
| Prometheus + Grafana | Dagster UI имеет мониторинг |

---

## ✅ Что НУЖНО сделать (минимум для безопасности)

### Уровень 1: Критично (делаем сейчас)
1. ✅ **HTTPS через Caddy** (автоматический Let's Encrypt)
2. ✅ **Firewall (UFW)** — только нужные порты
3. ✅ **Сильные пароли** в `.env`
4. ✅ **CORS whitelist** вместо `*`
5. ✅ **Автоматические backup БД** (cron + script)

### Уровень 2: Желательно (если есть время)
6. ⭕ Rate limiting (slowapi)
7. ⭕ Fail2ban
8. ⭕ Basic Auth на Dagster UI

---

## 🖥️ Шаг 1: Создание Droplet

### Рекомендуемая конфигурация

```
Droplet: Basic AMD
RAM: 4 GB (минимум), 8 GB (рекомендуется)
vCPUs: 2
Storage: 80 GB SSD
Region: Ближайший к вам (например, Frankfurt)
OS: Ubuntu 24.04 LTS
```

**Цена:** ~$24-48/месяц

### При создании droplet:
1. Добавьте SSH ключ (не используйте password authentication)
2. Включите "Monitoring" (бесплатно)
3. Включите "Backups" (+20%, ~$5/месяц) — опционально

---

## 🔧 Шаг 2: Настройка сервера

```bash
# Подключаемся к серверу
ssh root@YOUR_DROPLET_IP

# Обновляем систему
apt update && apt upgrade -y

# Устанавливаем Docker
curl -fsSL https://get.docker.com | sh

# Устанавливаем Docker Compose
apt install docker-compose-plugin -y

# Проверяем
docker --version
docker compose version
```

---

## 🔒 Шаг 3: Настройка Firewall (UFW)

```bash
# Включаем UFW
ufw default deny incoming
ufw default allow outgoing

# Разрешаем SSH
ufw allow 22/tcp

# Разрешаем HTTP/HTTPS (для Caddy)
ufw allow 80/tcp
ufw allow 443/tcp

# НЕ открываем напрямую:
# - 8000 (FastAPI) — через reverse proxy
# - 3000 (Dagster) — через reverse proxy
# - 3001 (Metabase) — через reverse proxy
# - 5432 (PostgreSQL) — внутренняя сеть Docker

# Включаем firewall
ufw enable

# Проверяем
ufw status
```

---

## 📁 Шаг 4: Настройка проекта

```bash
# Создаём директорию
mkdir -p /opt/process-metrics
cd /opt/process-metrics

# Клонируем репозиторий (или загружаем архив)
git clone https://github.com/YOUR_USER/process_metrics_platform_v2.git .

# Или скачиваем через scp с локальной машины:
# scp -r ./process_metrics_platform_v2/* root@YOUR_DROPLET_IP:/opt/process-metrics/
```

---

## 🔐 Шаг 5: Настройка переменных окружения

```bash
# Копируем пример
cp .env.example .env.production

# Генерируем безопасные пароли
apt install -y pwgen

# Генерируем пароли
POSTGRES_PASS=$(pwgen -s 32 1)
SECRET_KEY=$(openssl rand -hex 32)
MB_SECRET=$(openssl rand -hex 32)

echo "POSTGRES_PASSWORD: $POSTGRES_PASS"
echo "SECRET_KEY: $SECRET_KEY"
echo "MB_SECRET: $MB_SECRET"

# Записываем в .env.production (сохраните эти пароли!)
```

### Редактируем `.env.production`:

```bash
nano .env.production
```

```env
# =============================================================================
# Production Environment - DigitalOcean Droplet
# =============================================================================

# Database (используйте сгенерированный пароль!)
POSTGRES_DB=process_metrics
POSTGRES_USER=pmp_user
POSTGRES_PASSWORD=YOUR_GENERATED_STRONG_PASSWORD

# Application
ENVIRONMENT=production
LOG_LEVEL=WARNING
SECRET_KEY=YOUR_GENERATED_SECRET_KEY

# Jira (заполните свои данные)
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_USER_EMAIL=your-email@company.com
JIRA_API_TOKEN=your_jira_api_token

# Metabase
MB_ADMIN_EMAIL=admin@yourcompany.com
MB_ADMIN_PASSWORD=YOUR_STRONG_PASSWORD
METABASE_SECRET_KEY=YOUR_GENERATED_MB_SECRET

# Ports (внутренние, через reverse proxy)
APP_PORT=8000
DAGSTER_PORT=3000
METABASE_PORT=3001
```

---

## 🌐 Шаг 6: Настройка Reverse Proxy (Caddy)

Caddy автоматически получает SSL сертификаты от Let's Encrypt.

### Создаём `Caddyfile`:

```bash
nano /opt/process-metrics/Caddyfile
```

```caddyfile
# Замените YOUR_DOMAIN.com на ваш домен
# Или используйте nip.io для тестирования: YOUR_IP.nip.io

# Metabase (BI Dashboard) - основной интерфейс
metrics.YOUR_DOMAIN.com {
    reverse_proxy metabase:3000

    # Заголовки безопасности
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}

# Dagster UI (ETL мониторинг) - защищённый
dagster.YOUR_DOMAIN.com {
    # Basic Auth для Dagster UI
    basicauth * {
        admin $2a$14$YOUR_HASHED_PASSWORD
    }

    reverse_proxy dagster:3000

    header {
        X-Content-Type-Options "nosniff"
    }
}

# FastAPI (Admin Panel) - защищённый
api.YOUR_DOMAIN.com {
    reverse_proxy app:8000

    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }
}
```

### Генерируем хеш пароля для Basic Auth:

```bash
# Устанавливаем caddy локально для генерации хеша
docker run --rm caddy:alpine caddy hash-password --plaintext 'YOUR_PASSWORD'
# Вставьте результат в Caddyfile выше
```

---

## 🐳 Шаг 7: Docker Compose для Production

Создаём `docker-compose.simple.yml`:

```bash
nano /opt/process-metrics/docker-compose.simple.yml
```

```yaml
# =============================================================================
# Simple Production Deployment - DigitalOcean Droplet
# =============================================================================
#
# Usage: docker compose -f docker-compose.simple.yml up -d
#
# =============================================================================

networks:
  internal:
    driver: bridge

services:
  # ===========================================================================
  # Caddy - Reverse Proxy with Auto-SSL
  # ===========================================================================
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - internal
    depends_on:
      - app
      - dagster
      - metabase

  # ===========================================================================
  # PostgreSQL
  # ===========================================================================
  postgres:
    image: postgres:15-alpine
    container_name: postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - internal
    # НЕ открываем порт наружу!

  # ===========================================================================
  # FastAPI App
  # ===========================================================================
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: app
    restart: unless-stopped
    # НЕ открываем порт наружу - через Caddy
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      DAGSTER_GRAPHQL_URL: http://dagster:3000/graphql
      ENVIRONMENT: production
      LOG_LEVEL: ${LOG_LEVEL:-WARNING}
    env_file:
      - .env.production
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 512M

  # ===========================================================================
  # Dagster
  # ===========================================================================
  dagster:
    build:
      context: .
      dockerfile: Dockerfile.dagster
    container_name: dagster
    restart: unless-stopped
    # НЕ открываем порт наружу - через Caddy
    environment:
      DAGSTER_HOME: /opt/dagster/dagster_home
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      DAGSTER_POSTGRES_HOST: postgres
      DAGSTER_POSTGRES_USER: ${POSTGRES_USER}
      DAGSTER_POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      DAGSTER_POSTGRES_DB: ${POSTGRES_DB}
      DESTINATION__POSTGRES__CREDENTIALS__HOST: postgres
      DESTINATION__POSTGRES__CREDENTIALS__PORT: 5432
      DESTINATION__POSTGRES__CREDENTIALS__DATABASE: ${POSTGRES_DB}
      DESTINATION__POSTGRES__CREDENTIALS__USERNAME: ${POSTGRES_USER}
      DESTINATION__POSTGRES__CREDENTIALS__PASSWORD: ${POSTGRES_PASSWORD}
    env_file:
      - .env.production
    volumes:
      - dagster_home:/opt/dagster/dagster_home
      - ./config:/opt/dagster/app/config:ro
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/server_info"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 2G

  # ===========================================================================
  # Metabase
  # ===========================================================================
  metabase:
    image: metabase/metabase:latest
    container_name: metabase
    restart: unless-stopped
    # НЕ открываем порт наружу - через Caddy
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: ${POSTGRES_DB}
      MB_DB_PORT: 5432
      MB_DB_USER: ${POSTGRES_USER}
      MB_DB_PASS: ${POSTGRES_PASSWORD}
      MB_DB_HOST: postgres
      MB_ENCRYPTION_SECRET_KEY: ${METABASE_SECRET_KEY:-}
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 2G

volumes:
  postgres_data:
  dagster_home:
  caddy_data:
  caddy_config:
```

---

## 💾 Шаг 8: Автоматический Backup PostgreSQL

### Создаём скрипт backup:

```bash
mkdir -p /opt/process-metrics/scripts
nano /opt/process-metrics/scripts/backup_postgres.sh
```

```bash
#!/bin/bash
# =============================================================================
# PostgreSQL Backup Script
# =============================================================================

set -euo pipefail

# Конфигурация
BACKUP_DIR="/opt/backups/postgres"
CONTAINER_NAME="postgres"
DB_NAME="${POSTGRES_DB:-process_metrics}"
DB_USER="${POSTGRES_USER:-postgres}"
RETENTION_DAYS=14

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz"

# Создаём директорию если не существует
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting PostgreSQL backup..."

# Создаём backup
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

# Проверяем размер
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup created: $BACKUP_FILE ($BACKUP_SIZE)"

# Удаляем старые backup (старше RETENTION_DAYS)
find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] Old backups cleaned (older than $RETENTION_DAYS days)"

# Показываем текущие backup
echo "[$(date)] Current backups:"
ls -lh "$BACKUP_DIR"

echo "[$(date)] Backup completed successfully!"
```

```bash
# Делаем скрипт исполняемым
chmod +x /opt/process-metrics/scripts/backup_postgres.sh

# Настраиваем cron (ежедневно в 3:00)
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/process-metrics && source .env.production && /opt/process-metrics/scripts/backup_postgres.sh >> /var/log/pg_backup.log 2>&1") | crontab -
```

---

## 🔧 Шаг 9: Исправление CORS (критично!)

Нужно исправить в коде:

```bash
nano /opt/process-metrics/app/main.py
```

Найдите и замените:

```python
# ❌ БЫЛО:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ СТАЛО:
import os

ALLOWED_ORIGINS = [
    "https://metrics.YOUR_DOMAIN.com",
    "https://dagster.YOUR_DOMAIN.com",
    "https://api.YOUR_DOMAIN.com",
]

# Для development добавляем localhost
if os.getenv("ENVIRONMENT") != "production":
    ALLOWED_ORIGINS.extend([
        "http://localhost:3001",
        "http://localhost:8000",
        "http://localhost:3000",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## 🚀 Шаг 10: Запуск

```bash
cd /opt/process-metrics

# Собираем образы
docker compose -f docker-compose.simple.yml build

# Запускаем миграции
docker compose -f docker-compose.simple.yml run --rm app alembic -c db/migrations/alembic.ini upgrade head

# Запускаем все сервисы
docker compose -f docker-compose.simple.yml up -d

# Проверяем статус
docker compose -f docker-compose.simple.yml ps

# Смотрим логи
docker compose -f docker-compose.simple.yml logs -f
```

---

## ✅ Шаг 11: Проверка

### Проверяем сервисы:

```bash
# Все контейнеры запущены?
docker compose -f docker-compose.simple.yml ps

# Health check API
curl https://api.YOUR_DOMAIN.com/health

# Metabase доступен?
curl -I https://metrics.YOUR_DOMAIN.com

# SSL сертификат получен?
openssl s_client -connect metrics.YOUR_DOMAIN.com:443 -servername metrics.YOUR_DOMAIN.com </dev/null 2>/dev/null | openssl x509 -noout -dates
```

---

## 📊 Полезные команды

```bash
# Статус контейнеров
docker compose -f docker-compose.simple.yml ps

# Логи всех сервисов
docker compose -f docker-compose.simple.yml logs -f

# Логи конкретного сервиса
docker compose -f docker-compose.simple.yml logs -f dagster

# Перезапуск сервиса
docker compose -f docker-compose.simple.yml restart dagster

# Остановить всё
docker compose -f docker-compose.simple.yml down

# Полная пересборка
docker compose -f docker-compose.simple.yml up -d --build

# Backup вручную
/opt/process-metrics/scripts/backup_postgres.sh

# Восстановление из backup
gunzip -c /opt/backups/postgres/backup_YYYYMMDD_HHMMSS.sql.gz | docker exec -i postgres psql -U pmp_user -d process_metrics
```

---

## 🛡️ Дополнительная безопасность (опционально)

### Fail2ban для защиты SSH:

```bash
apt install fail2ban -y
systemctl enable fail2ban
systemctl start fail2ban
```

### Automatic Security Updates:

```bash
apt install unattended-upgrades -y
dpkg-reconfigure -plow unattended-upgrades
```

### IP Whitelist (если доступ только с определённых IP):

```bash
# Разрешаем только ваш офисный IP
ufw allow from YOUR_OFFICE_IP to any port 443
ufw delete allow 443/tcp
```

---

## 📝 Чеклист перед релизом

- [ ] Домен настроен (DNS A record → IP droplet)
- [ ] `.env.production` заполнен сильными паролями
- [ ] CORS исправлен на whitelist
- [ ] Firewall (UFW) включён
- [ ] SSL сертификаты получены (Caddy автоматически)
- [ ] Backup cron настроен
- [ ] Первый backup создан и проверен
- [ ] Все сервисы в статусе healthy
- [ ] Metabase настроен (создан admin аккаунт)
- [ ] Dagster синхронизирует данные с Jira

---

## 🆘 Troubleshooting

### Caddy не получает SSL:
```bash
# Проверьте DNS
dig metrics.YOUR_DOMAIN.com

# Порты 80/443 открыты?
ufw status

# Логи Caddy
docker compose -f docker-compose.simple.yml logs caddy
```

### PostgreSQL не стартует:
```bash
# Проверьте права на volume
ls -la /var/lib/docker/volumes/

# Логи PostgreSQL
docker compose -f docker-compose.simple.yml logs postgres
```

### Dagster не синхронизирует:
```bash
# Проверьте Jira credentials
docker compose -f docker-compose.simple.yml exec dagster env | grep JIRA

# Логи Dagster
docker compose -f docker-compose.simple.yml logs dagster
```

---

## 💰 Итоговая стоимость

| Ресурс | Цена |
|--------|------|
| DO Droplet 4GB | $24/мес |
| DO Droplet 8GB | $48/мес |
| Backups (+20%) | $5-10/мес |
| **Итого** | **$29-58/мес** |

Сравнение с enterprise решениями:
- AWS EKS + RDS + Redis: ~$375/мес
- **Экономия: 85%+**

---

## 🔄 Обновление платформы

```bash
cd /opt/process-metrics

# Получаем последние изменения
git pull origin main

# Пересобираем образы
docker compose -f docker-compose.simple.yml build

# Применяем миграции
docker compose -f docker-compose.simple.yml run --rm app alembic -c db/migrations/alembic.ini upgrade head

# Перезапускаем сервисы
docker compose -f docker-compose.simple.yml up -d
```

---

**Последнее обновление:** 2026-02-08
**Версия:** 1.0 (Simple Self-Hosted)
