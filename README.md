# Declarative FastAPI Backend Template

Работающий backend для отдельного Vue 3 Options API / TypeScript frontend.
Обычные поля описываются один раз в SQLModel; наш небольшой механизм ресурсов создаёт
Create/Patch/Read, список, стандартные HTTP-операции и OpenAPI. Сам frontend здесь не нужен.
Фабрика ресурсов — поддерживаемый код этого шаблона, с ограничениями, а не API FastAPI/SQLModel.

Стек: Python **3.14**, FastAPI, Pydantic 2/Settings, SQLModel, SQLAlchemy 2 Async,
asyncpg, PostgreSQL, Alembic, uv, Argon2id, HTTPX. Качество: Ruff, mypy, pytest, pre-commit.
Совместимые стабильные зависимости закреплены в `uv.lock`; prerelease не используются.

## От клонирования до работающего примера

Требуются Git, uv и PostgreSQL. Команды работают в PowerShell, Linux и macOS.

```sh
git clone https://github.com/SergTyapkin/python-backend-template
cd python-backend-template
uv sync --frozen
uv run project-init
```

Bootstrap создаёт `.env` и `.local/`, сохраняет существующие значения, устанавливает
только pre-commit. Сетевые провайдеры, администратор и данные при импорте не создаются.
Необходимые случайные session/CSRF tokens генерируются при входе; статический app secret не нужен.
Bootstrap запрещён в production.

Подключите локальный PostgreSQL: задайте `APP_DATABASE__URL` в `.env`.
Если Docker установлен и порт свободен, можно использовать только development-БД:

```sh
docker compose up -d postgres
uv run alembic upgrade head
uv run uvicorn myapp.main:create_app --factory --reload --no-proxy-headers
```

В другой консоли выполните полноценный сценарий:

```sh
uv run python scripts/example.py
```

Он явно создаёт двух обычных пользователей со случайными паролями, входит, создаёт задачу,
проверяет список владельца и PATCH, получает 404 от лица другого пользователя,
проверяет отключённый DELETE и выполняет logout. Это локальные данные примера; Task DELETE
намеренно не опубликован. Пользователей со стандартным паролем нет.

Открыты `/docs`, `/redoc`, `/openapi.json`, `/health/live`, `/health/ready`, `/version`.
Readiness делает короткий запрос к БД и возвращает 503 при недоступности;
liveness не зависит от PostgreSQL. Миграции не запускаются API workers.

## Структура

Сохранено имя Python-пакета `myapp`, чтобы не переносить исправную инфраструктуру:

```text
src/myapp/
  main.py              application factory / lifespan
  core/                CONFIG, settings, errors, dependencies, generated env reference
  db/                  shared metadata, async engine/session
  resources/           fields, schemas, Resource, router, policy, service
  modules/users/       закрытая SQLModel User, без универсального CRUD
  modules/auth/        Argon2, server sessions, cookie auth / CSRF
  modules/tasks/       одна декларация Task, owner policy, кастомизация create
  auth/                сохранённый независимый SSO JWT/JWKS verifier
  audit/               PostgreSQL audit trail в транзакции операции
  observability/       request ID, limits/timeouts, stdout logs
  jobs/                явная ручная cleanup-команда аудита, без scheduler
migrations/            Alembic: audit и 0002 users/sessions/tasks
contracts/openapi.json generated frontend contract
tests/unit/            генератор, доступ, ошибки, конфигурация, SSO
tests/integration/     реальные PostgreSQL / HTTP auth / ownership / rollback
scripts/               пример, quick tests, benchmark, pinned secret scanner
```

## Одна декларация и добавление поля

Реальный пример находится в `modules/tasks/models.py`:

```python
class Task(ResourceModel, table=True):
    id: UUID = api_field(default_factory=uuid4, primary_key=True, access=FieldAccess.READ_ONLY)
    title: str = api_field(min_length=1, max_length=200, access=FieldAccess.READ_WRITE)
    description: str | None = api_field(
        default=None, max_length=5000, access=FieldAccess.READ_WRITE
    )
    owner_id: UUID = api_field(foreign_key="app_user.id", index=True)
    # created_at объявлен здесь же как READ_ONLY с UTC default_factory.
```

`api_field` — типизированная ограниченная обёртка SQLModel Field. Типы, длины, числовые
границы, pattern, описание, default/factory, nullable и DB options находятся в этом объявлении.
Ограничение API не заменяет DB constraint: unique/FK обеспечиваются PostgreSQL и миграцией.

| FieldAccess | Create | Patch | Read |
|---|---|---|---|
| READ_WRITE | да | да | да |
| READ_ONLY | нет | нет | да |
| CREATE_ONLY | да | нет | нет |
| SERVER_ONLY, по умолчанию | нет | нет | нет |

Доступ не определяется по имени поля. Новое поле закрыто, пока доступ не разрешён явно.
Пароль относится к отдельному auth-сценарию; password_hash всегда закрыт.
User DTO тоже выводятся из декларации, password добавляется только к auth request.

Для нового поля измените SQLModel, создайте миграцию и экспортируйте контракт:

```sh
uv run project-migration "add task field"
# Обязательно прочитайте полученный файл миграции.
uv run alembic upgrade head
uv run export-openapi
```

Поле появляется в разрешённых схемах и OpenAPI без ручного редактирования DTO/TypeScript.
Для новой сущности добавьте импорт модели в `db/base.py:load_models`, создайте policy,
зарегистрируйте Resource и явно подключите его router в application factory.

## Правила Create / Patch / Read

Дополнительные правила задаются при регистрации без повторения типов:

```python
overrides = {
    "create": {"title": FieldOverride(constraints={"max_length": 100})},
    "patch": {"description": FieldOverride(include=False)},
}
```

Можно исключить поле, усилить ограничения, сделать поле обязательным.
Чтобы сделать Create/Read поле необязательным, нужен объявленный default/factory.
Ослабление ограничений, неизвестные поля и противоречащие правила отклоняются.
Расширение доступа поля требует `allow_access_expansion=True`; используйте его только после ревью.
Одновременные custom schema и generated overrides одной операции запрещены.

PATCH использует **`exclude_unset=True`**: omission не меняет поле, nullable допускает null,
non-nullable отвергает null. Read-only/server-only/create-only и неизвестные поля дают 422.
Пропущенные поля PATCH не запускают default_factory. Для omission используются стабильные
Pydantic defaults без их валидации; тип T не расширяется до T|None, OpenAPI default убирается.
Не применяйте обычный `model_dump()` частичной модели к ORM.

После объединения PATCH с заблокированной строкой валидируется **полное итоговое состояние**
через SQLModel.model_validate. Межполевые model validators не копируются в частичную схему.
Произвольные правила/нормализации реализуйте явно в service.

Можно передать `schemas={"create": MyCreate, "patch": MyPatch, "read": MyRead}`.
При нестандартных полях адаптируйте service; custom schemas также проверяются на расширение доступа.

## CRUD, policy и расширение

```python
tasks = Resource(
    model=Task,
    path="/tasks",
    operations={"list", "retrieve", "create", "patch"},
    policy=TaskPolicy(),
    service=TaskService(),
    sort_fields={"id", "title", "created_at"},
    filter_fields={"title"},
)
```

GET списка/записи и PATCH возвращают 200; POST — 201 и Read DTO; явный DELETE — 204 без тела.
DELETE у Task не включён и отсутствует в OpenAPI. PUT не добавляется.
Отключённые операции не регистрируются. Модели сами по себе ничего не публикуют.

Policy обязательна и по умолчанию закрывает доступ. TaskPolicy использует owner predicate
для списка, total и одной записи, а owner_id устанавливает из проверенного пользователя.
Недоступная и отсутствующая запись дают одинаковый 404. Роль не заменяет ownership.
Публичному ресурсу тоже нужны явная policy и principal_dependency.

Service не делает commit: function-scoped Session завершает транзакцию до отправки ответа,
rollback выполняется при исключении/cancellation. PATCH/DELETE блокируют строку FOR UPDATE.
Unique(owner_id, title) защищает от гонки; конфликт возвращает 409 без SQL/параметров.
Audit записывает разрешённые изменения той же транзакцией, с redaction и лимитом payload.

TaskService демонстрирует переопределение **create**: trim title и вызов super().create.
Другие операции наследуются. `handlers={"retrieve": custom_handler}` заменяет ровно один
handler; общая authentication/operation policy сохраняется. Объектную scope-проверку внутри
полностью custom handler должен выполнить сам handler/service.
Дополнительные маршруты подключаются обычным FastAPI router рядом с ресурсом.
Для сложной операции используйте обычные Pydantic DTO/service/SQLAlchemy без Resource.

Список: `{items, total, limit, offset}`, default limit=20, max=100.
COUNT и LIMIT/OFFSET выполняются в БД, сортировка всегда дополнена уникальным id.
Фильтры — только allowlist с точным равенством и типизированными query-параметрами;
sort allowlist виден в OpenAPI. Неизвестные query params дают 422. Вложенного CRUD отношений нет.

## Авторизация браузера и конфигурация

`POST /api/v1/auth/register`, `POST /login`, `GET /me`, `POST /logout` находятся под `/api/v1/auth`.
JSON для register/login: `{username, password}`. Пароли 12..128 символов хешируются Argon2id
в thread pool. Вход создаёт случайную 256-bit HttpOnly session cookie и возвращает csrf_token.
В БД хранятся хеши session/CSRF tokens, expires_at и user_id; logout отзывает сессию.
Cookie Secure во всех окружениях, кроме явно выбранного development; SameSite=Lax, Path=/.

Все изменяющие cookie-запросы требуют точный доверенный Origin и `X-CSRF-Token` из ответа login.
Register/login защищены строгим Origin и JSON-схемой до выдачи сессии.
Клиент использует `credentials: 'include'`; Vue и API в development используют **localhost**
на разных портах, чтобы не смешивать localhost и 127.0.0.1 как разные cookie sites.
CSRF храните в памяти клиента; после его потери нужен повторный вход. Восстановление токена,
refresh/session management UI и logout-all пока не реализованы.

`CONFIG` — типизированный alias декларации Settings, экземпляр создаётся factory.
Настройки сгруппированы: database, session, auth (SSO), audit, logging, email, integrations.
Env имеет APP_ prefix и __ delimiter, массивы — JSON. `.env.example` генерируется из
тех же деклараций: `uv run project-env`, актуальность — `uv run project-env --check`.
Существующий `.env` никогда не перезаписывается. Необходимая настройка при первом запуске — DB URL.

Production требует внешний DB URL с отдельным нестандартным credential, HTTPS public_url,
HTTPS CORS/session allowed_origins, session.allow_registration=false и выключенный debug.
Секреты передаются внешними env/secrets; имя cookie/TTL задаются реализацией и session settings.
Настройки, тела, credentials и query strings не выводятся в технические логи.

Сохранён JWT/JWKS SSO verifier и permission dependencies в `auth/`; Task использует локальную
сессию. Для внешнего SSO нужны явная identity mapping/policy и principal_dependency,
автоматического объединения локальных и внешних аккаунтов нет.

## OpenAPI и frontend

```sh
uv run export-openapi
uv run export-openapi --check
uv run openapi-spec-validator contracts/openapi.json
```

Экспорт детерминирован, использует declaration defaults, не подключается к БД и не читает секреты.
`contracts/openapi.json` помечен generated и хранится в Git; CI проверяет соответствие коду.
Передайте его в отдельный frontend repo для генерации TypeScript, клиента и runtime validators.
Поля JSON — **snake_case**, UUID — strings, datetime — UTC ISO 8601 с timezone.
Ошибки: `{code, message, details, request_id}`. Auth cookie описана в securitySchemes.
Контракт содержит ограничения, required/nullability, allowlists, пагинацию и стабильные operationId.
Примеры инструментов и пределы генерации — [docs/api-conventions.md](docs/api-conventions.md).

## Проверки, hooks и границы

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest tests/unit -q
# TEST_DATABASE_URL — отдельная PostgreSQL БД с суффиксом _test; данные удаляются!
uv run pytest tests/integration -q
uv run pre-commit run --all-files
uv build --no-sources
```

Для генератора/Task изменений hook запускает все unit-тесты генератора и доступа;
для остальных изменений — небольшой полный unit-suite. Нет сетевых аудитов, integration,
установки зависимостей и AI calls при commit. Установщик удаляет только старые Lefthook hooks.
Frozen CI включает Ruff/mypy, unit/PostgreSQL, реальные миграции и drift check, contract/env check,
package build, pip-audit/Bandit/Gitleaks. Dependabot поддерживает uv.lock и GitHub Actions.
Замеры: `uv run python scripts/benchmark.py`; условия/результаты — в docs/validation.md.

Механизм ограничен UUID id, плоскими column fields и явной регистрацией.
Динамические DTO имеют тип `type[BaseModel]`: mypy не выводит их атрибуты автоматически;
две фабрики аннотаций локально исключают valid-type, остальной код проверяется.
Для сложного типизированного сценария используйте обычную явную Pydantic-схему.
Трансформации/validators полной модели не превращаются в произвольные бизнес-операции.

Email verification/reset/OAuth, payments, WebSocket и боты — будущие обычные модули,
без пустых клиентов и фиктивного успеха. Security-правила расширения — docs/architecture.md.
Деплой, reverse proxy, backup, мониторинг, durable jobs и scheduler не реализованы.
Для production-входа отдельно необходим rate limiting/abuse control; ZAP — будущая ручная проверка
изолированного стенда. AI review — выключенный opt-in manual workflow, не замена CI.

Несовместимые изменения относительно 0.1: локальная auth и Task добавлены; JSON camelCase →
snake_case, list без hasNext; Pyright/Lefthook заменены mypy/pre-commit; ASGI entry point теперь
`myapp.main:create_app --factory`; контракт перенесён в contracts/. Audit migration 0001 сохранена.
