## Полный рецепт запуска Prefect Flow с задачами, деплойментами и ранами через Docker и API

### 📁 Структура проекта
```
project/
├── docker-compose.yml
├── flows/
│   └── complex_flow.py
└── scripts/
    └── deploy_and_run.py
```

---

### 🧩 1. Файл `flows/complex_flow.py`
```python
from prefect import flow, task

@task
def task_a(x: int) -> int:
    print(f"task_a: {x}")
    return x + 1

@task
def task_b(x: int) -> int:
    print(f"task_b: {x}")
    return x * 2

@task
def task_c(x: int) -> None:
    print(f"task_c got: {x}")

@flow
def complex_flow(start: int = 10):
    a = task_a(start)
    b = task_b(a)
    task_c(b)

if __name__ == "__main__":
    complex_flow()
```

---

### ⚙️ 2. Файл `scripts/deploy_and_run.py`

Этот скрипт полностью автоматизирует регистрацию flow, деплоймента, расписания и запуск.

```python
import requests
import sys
from datetime import datetime, timezone

API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://prefect-server:4200/api"
FLOW_NAME = "complex_flow"
HEADERS = {"x-prefect-api-version": "0.8.4", "Content-Type": "application/json"}

print(f"Using PREFECT API: {API_URL}")

# 1) Регистрируем Flow
print(f"-> Registering flow: {FLOW_NAME}")
flow_data = {"name": FLOW_NAME, "tags": ["demo"]}
r = requests.post(f"{API_URL}/flows/", json=flow_data, headers=HEADERS)
if r.status_code not in (200, 201):
    print(f"❌ Flow creation failed: {r.status_code}\n{r.text}")
    sys.exit(1)
flow_id = r.json()["id"]
print(f"✅ Flow registered: {flow_id}")

# 2) Создаём Deployment
print("-> Creating deployment (with entrypoint + path)...")
deployment_data = {
    "name": f"{FLOW_NAME}-deployment",
    "flow_id": flow_id,
    "work_pool_name": "default",
    "work_queue_name": "default",
    "path": "/opt/prefect/flows",
    "entrypoint": "complex_flow.py:complex_flow",
    "parameters": {},
    "tags": ["docker", "api"]
}
r = requests.post(f"{API_URL}/deployments/", json=deployment_data, headers=HEADERS)
if r.status_code not in (200, 201):
    print(f"❌ Deployment creation failed: {r.status_code}\n{r.text}")
    sys.exit(1)
deployment_id = r.json()["id"]
print(f"✅ Deployment created/updated: {deployment_id}")

# 3) Добавляем расписание (каждые 60 секунд)
print("-> Adding schedule (every 60s)...")
schedule_data = [
    {
        "active": True,
        "schedule": {
            "interval": 60.0,
            "anchor_date": datetime.now(timezone.utc).isoformat(),
            "timezone": "UTC"
        },
        "max_scheduled_runs": 50,
        "parameters": {}
    }
]
r = requests.post(f"{API_URL}/deployments/{deployment_id}/schedules", json=schedule_data, headers=HEADERS)
if r.status_code not in (200, 201):
    print(f"❌ Schedule creation failed: {r.status_code}\n{r.text}")
    sys.exit(1)
print("✅ Schedule added successfully!")

# 4) Запускаем вручную
print("-> Triggering manual run...")
r = requests.post(f"{API_URL}/deployments/{deployment_id}/create_flow_run", json={}, headers=HEADERS)
if r.status_code not in (200, 201):
    print(f"❌ Run creation failed: {r.status_code}\n{r.text}")
    sys.exit(1)
run_id = r.json()["id"]
print(f"✅ Flow run started: {run_id}")
```

---

### 🐳 3. Файл `docker-compose.yml`

```yaml
version: "3.9"

services:
  prefect-server:
    image: prefecthq/prefect:3.4.24-python3.11
    command: ["prefect", "server", "start", "--host", "0.0.0.0", "--ui"]
    ports:
      - "4200:4200"
    volumes:
      - ./flows:/opt/prefect/flows
      - ./scripts:/opt/prefect/scripts

  prefect-worker:
    image: prefecthq/prefect:3.4.24-python3.11
    depends_on:
      - prefect-server
    environment:
      PREFECT_API_URL: http://prefect-server:4200/api
    volumes:
      - ./flows:/opt/prefect/flows
      - ./scripts:/opt/prefect/scripts
      - /var/run/docker.sock:/var/run/docker.sock
    command: ["prefect", "worker", "start", "--pool", "default"]
```

---

### 🚀 4. Команды запуска

1️⃣ Собрать и запустить контейнеры:
```bash
docker compose up -d --build
```

2️⃣ Проверить, что сервер работает:
```bash
docker compose logs -f prefect-server
```

3️⃣ Запустить регистрацию и запуск flow:
```bash
docker compose exec prefect-worker python /opt/prefect/scripts/deploy_and_run.py http://prefect-server:4200/api
```

4️⃣ Проверить логи раннера:
```bash
docker compose logs -f prefect-worker
```

---

### ✅ Результат
- Prefect UI доступен по `http://localhost:4200`
- Flow `complex_flow` зарегистрирован и выполняется каждые 60 секунд.
- Можно вручную триггерить раны из UI или API.

---

### 💡 Кратко:
> Самый простой стабильный способ запускать Prefect Flow в Docker — через **API**:
> он не требует CLI-команд, registry, agent, work pool setup. Всё управляется скриптом `deploy_and_run.py`.
