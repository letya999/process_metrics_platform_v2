# Аудит Process Metrics Platform v2 — Action Items

**Режим:** 🏠 Self-Hosted (1 droplet DigitalOcean)
**Фокус:** Минимальная безопасность без enterprise-сложностей

---

## 🔴 КРИТИЧНО: Сделать ПЕРЕД деплоем (2-3 часа)

### 1. Настроить CORS на конкретные домены 🌐
**Время:** 15 минут

```python
# app/main.py — найти и изменить:

# ❌ БЫЛО:
allow_origins=["*"]

# ✅ СТАЛО:
allow_origins=[
    "https://metrics.your-domain.com",
    "https://dagster.your-domain.com",
    "https://api.your-domain.com",
    "http://localhost:3001",  # для локальной разработки
]
```

---

### 2. Сгенерировать сильные пароли 🔐
**Время:** 10 минут

```bash
# На сервере:
apt install pwgen -y

# Генерируем пароли
echo "POSTGRES_PASSWORD=$(pwgen -s 32 1)"
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "MB_SECRET=$(openssl rand -hex 32)"

# Записываем в .env.production
```

---

### 3. Настроить Firewall (UFW) 🛡️
**Время:** 10 минут

```bash
# На сервере:
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (для получения SSL)
ufw allow 443/tcp   # HTTPS
ufw enable

# Проверить: ufw status
```

---

### 4. Добавить Caddy для HTTPS 🔒
**Время:** 30 минут

Caddy автоматически получает SSL от Let's Encrypt.

```yaml
# Добавить в docker-compose:
caddy:
  image: caddy:2-alpine
  restart: unless-stopped
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./Caddyfile:/etc/caddy/Caddyfile:ro
    - caddy_data:/data
```

```caddyfile
# Caddyfile
metrics.your-domain.com {
    reverse_proxy metabase:3000
}
dagster.your-domain.com {
    basicauth * {
        admin $2a$14$HASHED_PASSWORD
    }
    reverse_proxy dagster:3000
}
api.your-domain.com {
    reverse_proxy app:8000
}
```

---

### 5. Убрать открытые порты из docker-compose ⚠️
**Время:** 10 минут

```yaml
# ❌ БЫЛО (порты наружу):
app:
  ports:
    - "8000:8000"

# ✅ СТАЛО (только внутренняя сеть):
app:
  # ports:  # Убираем или комментим!
  expose:
    - "8000"
```

Только Caddy должен иметь порты `80` и `443` наружу.

---

## 🟠 ЖЕЛАТЕЛЬНО: После деплоя (1-2 часа)

### 6. Настроить автоматический backup PostgreSQL 💾
**Время:** 20 минут

```bash
# /opt/process-metrics/scripts/backup.sh
#!/bin/bash
BACKUP_DIR="/opt/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
docker exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > $BACKUP_DIR/backup_$TIMESTAMP.sql.gz

# Удаляем старше 14 дней
find $BACKUP_DIR -name "*.sql.gz" -mtime +14 -delete
```

```bash
# Cron (ежедневно в 3:00):
chmod +x /opt/process-metrics/scripts/backup.sh
(crontab -l; echo "0 3 * * * /opt/process-metrics/scripts/backup.sh") | crontab -
```

---

### 7. Установить Fail2ban 🚫
**Время:** 5 минут

```bash
apt install fail2ban -y
systemctl enable fail2ban
systemctl start fail2ban
```

---

## ⚪ ОПЦИОНАЛЬНО: Когда будет время

### 8. Rate limiting на API
```python
# pyproject.toml — добавить:
dependencies = [..., "slowapi>=0.1.9"]

# app/main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.get("/metrics/velocity")
@limiter.limit("100/minute")
async def get_velocity(...):
    pass
```

### 9. Исправить failing тесты
```bash
.venv\Scripts\pytest --tb=short
# Исправить ошибки если нужно
```

### 10. Basic Auth для FastAPI (вместо JWT)
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, os.getenv("API_PASSWORD"))
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401)
    return credentials.username
```

---

## ❌ НЕ НУЖНО для self-hosted

Эти пункты из оригинального аудита **пропускаем**:

- ~~JWT + RBAC~~ → Basic Auth достаточно
- ~~Redis кэширование~~ → для 1-5 пользователей не нужно
- ~~Prometheus + Grafana~~ → смотреть Dagster UI
- ~~PostgreSQL replicas~~ → нет HA требований
- ~~Kubernetes~~ → 1 droplet
- ~~HashiCorp Vault~~ → env переменные
- ~~Dependabot~~ → обновлять вручную раз в месяц

---

## 📋 Чеклист деплоя

```
Перед первым запуском:
- [ ] DNS записи указывают на droplet IP
- [ ] UFW firewall включён
- [ ] Сильные пароли в .env.production
- [ ] CORS исправлен (убрать *)
- [ ] Caddyfile создан

После запуска:
- [ ] docker compose up -d работает
- [ ] HTTPS работает (https://metrics.your-domain.com)
- [ ] Metabase открывается
- [ ] Dagster UI доступен (через Basic Auth)
- [ ] Первый backup создан и проверен
```

---

## 📞 Если что-то сломалось

```bash
# Логи всех сервисов
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f dagster

# Перезапуск
docker compose restart

# Полный рестарт
docker compose down && docker compose up -d
```

---

**Версия:** 2.0 (Simplified for Self-Hosted)
**Последнее обновление:** 2026-02-08
