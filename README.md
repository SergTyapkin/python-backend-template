# Python Backend Template

Чистый modular monolith для коммерческих проектов с отдельным Nuxt 4 frontend
и внешним SSO. Бизнес-моделей, локальных пользователей и демонстрационного CRUD нет.

Стек: Python 3.14, FastAPI, Pydantic 2/Settings, SQLAlchemy 2 Async,
PostgreSQL, asyncpg, Alembic, uv, Uvicorn, PyJWT, HTTPX.
Качество: Ruff, Pyright, pytest, Lefthook, GitHub Actions.
Точные совместимые версии находятся в `uv.lock`; обновление — `uv lock --upgrade` с ревью CI.

## Быстрый запуск

Нужны uv, Git и PostgreSQL 18 (локально либо Docker).
Команды работают из корня проекта в PowerShell, Bash и других оболочках:

```sh
uv sync --locked
uv run project-init
# Необязательно: локальная БД, если порт 5432 свободен
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn myapp.main:app --reload --no-proxy-headers
```

`project-init` создаёт `.env`, `.local/` и hooks, не перезаписывает `.env`;
не применяется к production. Если PostgreSQL установлен отдельно, задайте его
URL в `.env`; Compose использует только локальные development credentials.
Не требуется frontend или фиктивный пользователь.

Доступны `/health/live`, `/health/ready`, `/version`, `/docs`, `/redoc`, `/openapi.json`.
Основной namespace `/api/v1` пуст до явного подключения бизнес-модуля.
Liveness не зависит от БД. Readiness выполняет короткий `SELECT 1`, отдаёт 503 при сбое.
Миграции проверяются отдельным шагом, readiness не гарантирует актуальность схемы.

## Настройки

`Settings` в `core/config.py` типизирован, поддерживает autocomplete и вложенные env:
`APP_DATABASE__URL`, `APP_AUTH__ISSUER`, `APP_LOGGING__LEVEL`.
Массивы/словари задаются JSON; полный стартовый набор в `.env.example`.
`.env` игнорируется Git. В production передавайте env/secrets извне,
`APP_ENVIRONMENT=production`, HTTPS public URL и отдельные DB credentials.
Production запрещает debug, wildcard CORS и стандартный пароль БД.
Email/integrations optional; клиентов и сетевых вызовов по умолчанию нет.

## Структура

```text
src/myapp/
  main.py          # application factory и lifespan
  core/            # settings, DI, errors, security
  api/             # routers, DTO, pagination, permissions
  db/              # metadata, engine, session factory
  auth/            # Principal, JWT verifier, JWKS cache
  audit/           # infrastructure model, redaction, transaction-safe service
  observability/   # structured logs, request limits/timeouts
  modules/         # будущие бизнес-модули
  integrations/    # будущие внешние клиенты
  jobs/            # standalone infrastructure jobs
migrations/        # Alembic, initial audit schema
tests/unit/        # без внешних сервисов
tests/integration/ # настоящий PostgreSQL
scripts/           # вспомогательные инструкции запуска проверок
docs/              # практические мини-инструкции
```

## Новая сущность и CRUD

1. Создайте `modules/<name>/models.py`, наследуйте `db.base.Base`.
2. Добавьте импорт модели в `load_models()` для Alembic.
3. Создайте Create/Patch/Read DTO от `api.responses.Schema`.
4. Выполните `uv run project-migration "add resource"`; проверьте migration.
5. Примените `uv run alembic upgrade head`.
6. Создайте service, отдельные permissions и объектную проверку доступа.
7. Создайте router с GET/POST/PATCH/DELETE; используйте `Session` и публичные Read DTO.
8. Подключите audit в той же транзакции и router в `api/router.py`.
9. Добавьте тесты валидации, прав, rollback и PostgreSQL queries.
10. Экспортируйте контракт для frontend.

Не открывайте все ORM-модели автоматически. Подробные короткие примеры —
[architecture.md](docs/architecture.md).

PATCH: `payload.model_dump(exclude_unset=True)` различает отсутствие поля и `null`.
Обязательные DB-поля не должны становиться nullable из-за Patch DTO: проверяйте явный null.
PUT в шаблоне не используется.

Списки: `{items, total, limit, offset, hasNext}`, limit по умолчанию 20, максимум 100.
`paginate()` делает COUNT/LIMIT/OFFSET на стороне БД. Фильтры определяются DTO модуля,
сортировка — whitelist SQLAlchemy columns; добавляйте уникальный tie-breaker.

## Миграции и PostgreSQL

```sh
uv run project-migration "describe change"
uv run alembic upgrade head
uv run alembic check
```

Initial migration создаёт только `audit_log` и индексы.
Autogenerate не распознаёт переименование надёжно: всегда проверяйте SQL,
удаления, nullable/default и data migrations. Не запускайте миграции в API lifespan.
В будущем CI/CD использует отдельный migration job с отдельными DDL credentials.
Runtime DB user должен иметь минимальные права; не используйте superuser.

## SSO, Nuxt BFF и permissions

Задайте `APP_AUTH__ISSUER`, `APP_AUTH__AUDIENCE` и при необходимости
`APP_AUTH__JWKS_URL`; иначе используется OIDC discovery. HTTPS обязателен.
Проверяются подпись, algorithm whitelist, issuer, audience, exp, iat, nbf при наличии,
обязательные и ожидаемые claims. `expected_claims` позволяет требовать признак access token
вашего SSO. Нельзя считать произвольный JWT или ID token подходящим access token.
JWKS кэшируется, unknown kid обновляет ключи с ограничением частоты; outage закрывает доступ.

Используйте `CurrentPrincipal`, `require_authenticated`, `require_scopes`,
`require_permissions` и объектные проверки в service. Пример в architecture.md.
Глобальные роли живут в SSO; локальные permissions/ownership определяет проект.
Роль сама по себе не разрешает доступ к чужой записи.
Без настроенного SSO public endpoints работают, protected endpoints закрыты.

Nuxt BFF хранит browser session, выполняет CSRF-защиту и передаёт Bearer access token.
API не принимает cookie-auth и не доверяет X-User-ID. Если появится cookie-auth,
обязательна CSRF-защита API. Trusted proxies задаются явно при запуске Uvicorn.

## Audit и логи

`record_audit(session, settings.audit, ...)` пишет короткий JSONB в текущей транзакции.
Передавайте только allowlist изменённых полей, используйте `exclude` для чувствительных данных.
Есть глобальное отключение, excluded_entities, actions, рекурсивная redaction и лимит payload.
Не передавайте полные объекты, бинарные данные, credentials или PII.
`project-job audit-cleanup` удаляет записи старше retention_days порциями;
архивирование при необходимости выполняйте перед удалением внешней задачей.

Production пишет JSON в stdout; development — читаемый текст.
Логи содержат request ID, method, route template, status, duration, тип исключения.
Тела, headers, query strings и exception messages автоматически не пишутся.
Уровень и access logging настраиваются. Место для OpenTelemetry — application factory.

## Интеграции и фоновые задачи

HTTP clients создавайте в lifespan и передавайте через Depends; ограничивайте timeout,
ошибки переводите в AppError, тестируйте MockTransport/fake. Пример — architecture.md.
Для Email, Telegram, Payments и WebSocket пока оставлено только место расширения.
Короткие некритичные действия допустимы через BackgroundTasks; они не гарантируют доставку.
Для регулярных задач добавляйте явные команды в jobs/cli.py, запускайте внешним scheduler.
Cron внутри API запрещён. Для критичных задач позже добавляется durable queue/outbox.

## Контракт, проверки и hooks

```sh
uv run export-openapi
uv run openapi-spec-validator .local/contracts/openapi.json
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests/unit -q
# Задайте TEST_DATABASE_URL на отдельную БД с суффиксом _test!
uv run pytest tests/integration -q
```

Интеграционные тесты пересоздают схему audit через downgrade/upgrade Alembic;
не используйте рабочую БД. Примеры env для PowerShell/Linux — development.md.
Hooks ставятся project-init. Pre-commit: staged Ruff, config/secrets, релевантный unit smoke.
Pre-push: только быстрый secret/config check. Основной quality gate — CI:
Ruff, Pyright, pytest/PostgreSQL, Alembic check, OpenAPI, pip-audit, Bandit, Gitleaks.
Windows/macOS unit matrix проверяет переносимость. Dependabot обновляет uv и Actions.

AI review выключен. Для opt-in задайте repository variable `ENABLE_AI_REVIEW=true`,
`AI_REVIEW_MODEL` и отдельный secret `AI_REVIEW_API_KEY`, затем запустите workflow вручную.
Это платный opt-in: diff отправляется провайдеру; PR-код не исполняется, права read-only,
результат находится в summary и не заменяет CI. Production secrets не передавать.

## Будущая инфраструктура

Deployment не включён. API, migration и jobs готовы к раздельному запуску,
env injection, внешнему PostgreSQL, нескольким инстансам и graceful shutdown.
Состояние API не зависит от локальных файлов. Контейнер, reverse proxy,
secrets manager, storage, observability, CI/CD и rollback настраиваются отдельно.
Перед внешним релизом настройте upstream rate/body limits и при необходимости OWASP ZAP.
Подробности: [API conventions](docs/api-conventions.md), [development](docs/development.md).
