# Архитектура Process Metrics Platform v2

**Режим:** 🏠 Self-Hosted (1 droplet DigitalOcean)

---

## Текущая архитектура (AS-IS)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Пользователь (браузер)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                    HTTP (без HTTPS) ⚠️
                              │
┌─────────────────────────────┼─────────────────────────────────────┐
│                         Docker Host                               │
│                              │                                    │
│  ┌───────────────────────────┼───────────────────────────────┐   │
│  │                           │                               │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │   │
│  │  │  Metabase  │  │  Dagster   │  │   FastAPI App      │  │   │
│  │  │   :3001    │  │   :3000    │  │      :8000         │  │   │
│  │  └────────────┘  └────────────┘  └────────────────────┘  │   │
│  │         │              │                   │              │   │
│  │         └──────────────┼───────────────────┘              │   │
│  │                        │                                  │   │
│  │                   PostgreSQL                              │   │
│  │                     :5432                                 │   │
│  │                                                           │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ⚠️ Проблемы:                                                     │
│  • Порты открыты напрямую наружу                                 │
│  • Нет HTTPS                                                     │
│  • CORS = "*"                                                    │
│  • Нет backup                                                    │
└───────────────────────────────────────────────────────────────────┘
```

---

## Целевая архитектура (TO-BE) — Простой Self-Hosted

```
┌─────────────────────────────────────────────────────────────────┐
│                     Пользователь (браузер)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                         HTTPS ✅
                              │
┌─────────────────────────────┼─────────────────────────────────────┐
│                      DigitalOcean Droplet                         │
│                              │                                    │
│                     UFW Firewall ✅                               │
│                    (только 22, 80, 443)                          │
│                              │                                    │
│  ┌───────────────────────────┼───────────────────────────────┐   │
│  │                    Caddy (Reverse Proxy)                   │   │
│  │                   Auto-SSL Let's Encrypt ✅                │   │
│  │                                                           │   │
│  │    metrics.domain.com → Metabase                         │   │
│  │    dagster.domain.com → Dagster (Basic Auth)             │   │
│  │    api.domain.com     → FastAPI                          │   │
│  └───────────────────────────┼───────────────────────────────┘   │
│                              │                                    │
│  ┌───────────────────────────┼───────────────────────────────┐   │
│  │               Docker Internal Network                      │   │
│  │                                                           │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │   │
│  │  │  Metabase  │  │  Dagster   │  │   FastAPI App      │  │   │
│  │  │  (internal)│  │  (internal)│  │   (internal)       │  │   │
│  │  └────────────┘  └────────────┘  └────────────────────┘  │   │
│  │         │              │                   │              │   │
│  │         └──────────────┼───────────────────┘              │   │
│  │                        │                                  │   │
│  │                   PostgreSQL                              │   │
│  │                   (internal only)                         │   │
│  │                                                           │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ✅ Backup: cron + pg_dump → /opt/backups/                       │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘

                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Jira Cloud (API)                          │
│                    Синхронизация через Dagster                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
Jira Cloud
    │
    │ HTTPS + API Token
    ▼
┌──────────────┐
│   Dagster    │ ← Расписание (schedules)
│   ETL Jobs   │
└──────────────┘
    │
    │ 1. Raw data (raw_jira schema)
    │ 2. Clean data (clean_jira schema)
    │ 3. Metrics (metrics schema)
    ▼
┌──────────────┐
│  PostgreSQL  │
└──────────────┘
    │
    ▼
┌──────────────┐     ┌──────────────┐
│   Metabase   │     │   FastAPI    │
│ (Dashboards) │     │   (Admin)    │
└──────────────┘     └──────────────┘
```

---

## Что НЕ нужно для self-hosted

| Enterprise-компонент | Замена для self-hosted |
|---------------------|------------------------|
| Kubernetes | Docker Compose |
| AWS RDS | PostgreSQL в Docker |
| Redis cluster | Не нужен |
| Vault | Env-переменные |
| Prometheus + Grafana | Dagster UI + логи |
| AWS ALB | Caddy |
| K8sRunLauncher | DefaultRunLauncher ОК |

---

## Минимальный docker-compose

```yaml
services:
  caddy:
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro

  postgres:
    image: postgres:15-alpine
    # БЕЗ ports: - только внутренняя сеть

  app:
    build: .
    # БЕЗ ports: - через Caddy

  dagster:
    build:
      dockerfile: Dockerfile.dagster
    # БЕЗ ports: - через Caddy

  metabase:
    image: metabase/metabase:latest
    # БЕЗ ports: - через Caddy
```

---

## Security Improvements (минимум)

| Было | Стало |
|------|-------|
| `allow_origins=["*"]` | Конкретные домены |
| HTTP | HTTPS (Caddy auto-SSL) |
| Порты открыты | UFW firewall |
| Нет backup | Cron + pg_dump |
| Weak passwords | pwgen -s 32 |

---

## Стоимость

```
DigitalOcean Droplet (4GB RAM):  $24/мес
Backups (+20%):                   $5/мес
─────────────────────────────────────────
Итого:                           $29/мес

vs Enterprise (K8s + RDS + Redis): ~$375/мес
Экономия: 92%
```

---

**Версия:** 2.0 (Simplified for Self-Hosted)
**Последнее обновление:** 2026-02-08
