Searched the web, ran 2 commands, read a file
Searched the web, ran 2 commands, read a file

The agent is still running. Let me fetch additional relevant information in parallel while waiting.


Searched the web
Searched the web

Now let me compile all the research findings. I have enough information for a comprehensive answer.

Глубокий ресерч: Pre-built Metabase дашборды в open-source проекте
TL;DR
Да, можно. Для OSS Metabase лучший путь — программное создание дашбордов через REST API при первом запуске. Сериализация (YAML-экспорт) требует Pro/Enterprise.

1. Два принципиально разных подхода
Подход А: Serialization (YAML-файлы) — ТОЛЬКО Pro/Enterprise
Metabase умеет экспортировать весь контент (дашборды, вопросы, модели, коллекции) в YAML-файлы через:

CLI: java -jar metabase.jar export ./bundle
API: POST /api/ee/serialization/export
Файлы можно положить в git и импортировать на новом инстансе. Но это платная функция (Pro от $500/мес или self-hosted Pro). Для open-source дистрибуции с бесплатным Metabase OSS — не подходит.

Подход Б: REST API — РАБОТАЕТ в OSS (БЕСПЛАТНО)
Metabase REST API полностью доступен в бесплатной OSS версии. Можно написать setup-скрипт, который:

Ждёт, пока Metabase поднимется (GET /api/health)
Аутентифицируется через API key или username/password
Создаёт все объекты через API
Ключевые эндпоинты:

POST /api/database          - подключить базу данных
POST /api/collection        - создать коллекцию
POST /api/card              - создать карточку/вопрос
POST /api/dashboard         - создать дашборд
POST /api/dashboard/:id/cards - добавить карточки в дашборд с позиционированием
PUT  /api/dashboard/:id     - обновить дашборд

2. Готовые Python-библиотеки
metabase-api (PyPI) — рекомендуемая
pip install metabase-api

Обёртка над REST API, MIT-лицензия, активно поддерживается (последнее обновление март 2026)
Ключевые методы:
mb = Metabase_API('http://localhost:3000', api_key='YOUR_KEY')
mb.create_card(card_name='Cycle Time', table_name='metrics_jira')
mb.create_dashboard(dashboard_name='Engineering Metrics')
mb.copy_dashboard(source_dashboard_id=1, destination_collection_id=2)

Поддерживает deepcopy дашбордов (клонирует карточки), создание коллекций, поиск объектов
Другие варианты:
metabasepy — REST API клиент (81 звезда)
metabase-py — ещё один враппер (50 звёзд)
metabase_export_import — специализирован на экспорте/импорте конфигурации
3. Скилл skills.sh/vasilyu1983/ai-agents-public/data-metabase
Скилл предоставляет scripts/metabase_api.py — dependency-free helper (без внешних зависимостей). Он умеет:

Команда	Что делает
whoami	Проверить аутентификацию (API key или session)
health	Проверить доступность API
export-card --id N --out file.json	Экспортировать существующую карточку как JSON-шаблон
export-dashboard --id N --out file.json	Экспортировать существующий дашборд как JSON-шаблон
upsert-card --spec file.json	Создать/обновить карточку из JSON-спецификации
upsert-dashboard --spec file.json	Создать/обновить дашборд из JSON-спецификации
Workflow для вашего проекта с этим скиллом:

Создаёшь дашборд вручную в Metabase
Экспортируешь через export-dashboard → получаешь JSON
Кладёшь JSON в репозиторий
При первом запуске пользователя → setup-скрипт вызывает upsert-dashboard с этим JSON
Скилл решает проблему hardcoded ID — находит объекты по имени, а не по числовым ID (которые будут разными у каждого пользователя).

4. Рекомендуемая архитектура для вашего OSS-проекта
repo/
  scripts/
    metabase_setup.py        # setup-скрипт
    metabase_api.py          # helper из скилла
  metabase/
    specs/
      collection_engineering.json
      card_cycle_time.json
      card_throughput.json
      dashboard_engineering_metrics.json

setup-скрипт запускается после docker-compose up и:

Поллит /api/health до готовности
Читает JSON-спецификации из metabase/specs/
Создаёт объекты через API (idempotent через upsert)
Настраивает подключение к PostgreSQL
Интеграция в docker-compose.simple.yml:

metabase-setup:
  image: python:3.11-slim
  depends_on:
    metabase:
      condition: service_healthy
  command: python /scripts/metabase_setup.py
  volumes:
    - ./scripts:/scripts
    - ./metabase/specs:/specs

5. Главные выводы
Вопрос	Ответ
Создать дашборд вручную и распространять?	Нет прямого экспорта в OSS. Нужен JSON через API или скилл
Создавать дашборды программно?	Да, полностью, через REST API — работает в бесплатном OSS
Serialization (YAML)?	Только Pro/Enterprise, не для OSS-дистрибуции
Python-библиотека	metabase-api (PyPI) или скрипт из скилла
Скилл data-metabase полезен?	Да — export-dashboard для получения JSON-шаблона, upsert-dashboard для воспроизведения
IDs — проблема?	Да, числовые ID разные у каждого пользователя. Скилл решает через lookup по имени
Практический план
Использовать скилл для экспорта текущих/желаемых дашбордов в JSON
Написать scripts/metabase_setup.py используя metabase_api.py из скилла
Добавить сервис metabase-setup в docker-compose.simple.yml
При первом запуске пользователем — скрипт автоматически создаёт все дашборды
Это полностью решает задачу и работает с бесплатным OSS Metabase.

Отличный результат от фонового агента. Вот полный сводный ресёрч:

Итоговый глубокий ресёрч: Pre-built Metabase дашборды в OSS-проекте
Главный вывод
Да, можно полностью. Для бесплатного Metabase OSS правильный путь — программное создание дашбордов через REST API при первом запуске. Никаких платных фич не нужно.

Два принципиально разных подхода
Подход А: Serialization (YAML/JSON экспорт) — ТОЛЬКО Pro/Enterprise
Встроенный механизм Metabase для переноса дашбордов между инстансами. Экспортирует всё в YAML, можно хранить в git.

Требует: Pro план ($500+/мес) или self-hosted Pro
Для OSS-дистрибуции: не подходит
Единственный OSS-альтернатив сериализации — библиотека 24eme/metabase_export_import (делает то же самое через API, экспортирует в JSON, работает на community edition).

Подход Б: REST API — РАБОТАЕТ в бесплатном OSS
Весь UI Metabase работает через свой же REST API. Он полностью доступен в OSS, без каких-либо ограничений на CRUD-операции.

Ключевые эндпоинты:

POST /api/session/properties    → получить setup-token (первый запуск)
POST /api/setup                 → создать первого admin (headless bootstrap)
POST /api/database              → подключить PostgreSQL
POST /api/database/:id/sync_schema → синхронизировать схему
POST /api/collection            → создать коллекцию
POST /api/card                  → создать карточку/вопрос с графиком
POST /api/dashboard             → создать дашборд
PUT  /api/dashboard/:id         → добавить карточки + позиционирование (актуально с v0.47+)

Важное изменение API в v0.47+: старый POST /api/dashboard/:id/cards удалён без предупреждения. Сейчас для добавления карточек используется PUT /api/dashboard/:id с полным массивом dashcards.

Готовые инструменты
Python-библиотеки
Библиотека	Звёзды	Назначение
metabase-api (vvaezian)	161	Наиболее полный враппер. create_card(), copy_dashboard(deepcopy=True), clone_card()
metabase-python (chasleslr)	~50	ORM-стиль: Dashboard.list(), Card.create(), Pandas DataFrames
metabase_export_import (24eme)	~30	Экспорт/импорт дашбордов как JSON между инстансами (OSS-альтернатива сериализации)
# metabase-api пример
from metabase_api import Metabase_API
mb = Metabase_API('http://localhost:3000', api_key='YOUR_KEY')
mb.create_card(card_name='Cycle Time', table_name='metrics_jira')
mb.copy_dashboard(source_dashboard_id=1, destination_collection_id=5, deepcopy=True)

Dashboard-as-code инструменты
Metastasis (Ruby gem) — DSL для определения дашбордов как кода, деплой через metastasis apply -e production
EmbedKit (Clojure) — content-addressed кэширование, динамическая генерация дашбордов на инстанс/тенант
Реальные примеры OSS-проектов со встроенными дашбордами
echodelta123/heycar-case-study — bootstrap.py (~200 строк):

Поллит /api/health до готовности
POST /api/setup → создаёт первого admin headless
Подключает DuckDB
Создаёт 5 дашбордов с 37 карточками
Идемпотентен (upsert по имени)
Запускается через docker-compose
Fatih0234/01-github-backlog-issues — setup_metabase.py:

16 карточек (KPI, time series, bar charts) против gold-layer схемы
Полностью через PUT /api/dashboard/:id с dashcards
Скилл skills.sh/vasilyu1983/ai-agents-public/data-metabase
Это AI agent skill (инструкционный набор для Claude Code / Codex), а не standalone-библиотека.

Что умеет:

Дать агенту (Claude) процедурные знания для работы с Metabase API
export-dashboard --id N --out file.json → экспортировать существующий дашборд как JSON-шаблон
upsert-dashboard --spec file.json → создать/обновить дашборд из JSON-спецификации
Решает проблему hardcoded ID — ищет объекты по именам, а не числовым ID
Установка: npx skills add https://github.com/vasilyu1983/ai-agents-public --skill data-metabase

Workflow с этим скиллом:

Создаёшь дашборд вручную в Metabase
Скилл его экспортирует в JSON-шаблон
JSON кладётся в репозиторий
При первом запуске → скрипт upsert-dashboard воспроизводит дашборд
Рекомендованный план для Process Metrics Platform v2
scripts/
  provision_metabase.py      # setup-скрипт (Python + requests, без зависимостей)
metabase/
  specs/
    card_cycle_time.json
    card_throughput.json
    card_lead_time.json
    dashboard_engineering_metrics.json

docker-compose.simple.yml интеграция:

metabase-setup:
  image: python:3.11-slim
  depends_on:
    metabase:
      condition: service_healthy
  volumes:
    - ./scripts:/scripts
    - ./metabase/specs:/specs
  command: python /scripts/provision_metabase.py
  environment:
    - METABASE_URL=http://metabase:3000
    - METABASE_API_KEY=${METABASE_API_KEY}

Скрипт делает:

Поллит /api/health
На первом запуске — POST /api/setup headless
Подключает metrics схему PostgreSQL
Загружает JSON-спецификации карточек и дашбордов
Создаёт всё через API идемпотентно (upsert по имени)
Никаких платных фич. Работает с бесплатным Metabase OSS. Реальные примеры в продакшне существуют.

"Экспортируешь через export-dashboard → получаешь JSON" каким образом, через что? У меня free версия



Searched the web, loaded tools
Searched the web, loaded tools

Теперь у меня есть реальный исходный код. Отвечаю честно и точно.

Как работает export-dashboard — без магии
export-dashboard делает ровно одно: вызывает стандартный REST API вашего Metabase:

def cmd_export_dashboard(args):
    _, headers = _pick_auth_headers()
    status, payload, raw = _request("GET", f"/api/dashboard/{args.id}", headers)
    # ...
    json.dump(payload, f, ...)  # сохраняет ответ в файл

То есть это просто GET /api/dashboard/:id → сохранить JSON в файл. Никаких платных фич, работает в бесплатном OSS.

Проблема: в JSON будут числовые ID вашего инстанса
Пример того, что вернёт GET /api/dashboard/5:

{
  "id": 5,
  "name": "Engineering Metrics",
  "dashcards": [
    {
      "card_id": 12,        ← ID карточки на ВАШЕМ инстансе
      "col": 0, "row": 0,
      "size_x": 4, "size_y": 4
    }
  ]
}

У пользователя вашего open-source проекта эти ID будут другими. upsert-dashboard тупо сделает PUT /api/dashboard/:id с этим же JSON — и сломается, потому что card_id: 12 у него не существует.

Скрипт не решает проблему ID сам по себе. Это задача агента (Claude), который при использовании скилла должен:

Сначала создать все карточки на новом инстансе
Запомнить их новые ID
Подставить в JSON дашборда перед upsert-dashboard
Как правильно использовать для дистрибуции
Вариант 1 (проще): хранить карточки как SQL + конфиг, а не как экспортированный JSON

metabase/
  cards/
    cycle_time.json        ← содержит SQL-запрос, display, settings (без card_id)
    throughput.json
  dashboards/
    engineering.json       ← содержит layout (col/row/size), без hardcoded card_id

Setup-скрипт:

Создаёт карточки через POST /api/card → получает реальные ID
Патчит layout дашборда с полученными ID
Создаёт дашборд через POST /api/dashboard
Вариант 2 (быстрее запустить): использовать скилл через Claude

# Запускаешь Claude Code со скиллом data-metabase
# Агент сам:
# - экспортирует дашборд
# - пересоздаёт его на чистом инстансе с правильным ID-маппингом

Итог
Вопрос	Ответ
export-dashboard использует платный API?	Нет — это просто GET /api/dashboard/:id, бесплатно
Экспортированный JSON сразу перенесёшь к пользователю?	Нет — числовые ID будут неправильными
Скрипт решает проблему ID?	Нет — это задача агента или твоего setup-скрипта
Рабочий путь для OSS-дистрибуции	Хранить карточки как SQL-спецификации, setup-скрипт создаёт всё с нуля
Для твоего проекта наиболее надёжный путь — написать scripts/provision_metabase.py, который создаёт все карточки и дашборды с нуля через API, не завися от переносимости экспортированных ID.

Sources:

vasilyu1983/AI-Agents-public — GitHub
