# Development и проверки

`uv sync --locked` воспроизводит зависимости; `uv lock --upgrade` обновляет после ревью.
Python 3.14 выбран как стабильная версия, совместимая с asyncpg/cryptography и текущим uv.
Проверяйте поддержку wheels перед сменой minor Python; prerelease не используйте.

## Отдельная тестовая БД

Создайте отдельную пустую PostgreSQL БД `app_test` и её владельца средствами вашей установки.
Тесты удаляют и создают инфраструктурные таблицы через Alembic; нужен DDL доступ.
Тестовый URL не должен указывать на рабочую БД. Сuffix `_test` проверяется автоматически.

PowerShell:

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/app_test'
uv run pytest tests/integration -q
```

Linux/macOS:

```sh
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q
```

Без TEST_DATABASE_URL интеграционные тесты явно skipped; unit не требуют БД.
Для чистой production-like проверки примените upgrade head на новой БД,
повторите upgrade, затем alembic check. Не применяйте downgrade к данным проекта.

## Hooks и CI

`uv run project-init` вызывает `lefthook install`. Повторно: `uv run lefthook install`.
`uv run lefthook run pre-commit` проверяет staged файлы; форматирование не меняет index.
Исправление: `uv run ruff check --fix <files>`, `uv run ruff format <files>`, затем git add.
Конфиги проверяются на синтаксис, final newline и trailing spaces, secrets — по staged bytes.
Это быстрый detector, не замена Gitleaks/ревью. Pre-push не запускает полный quality gate.
Новые виды секретов добавляйте в detector и CI policy, реальные значения не коммитьте.

CI не деплоит, имеет contents:read, использует PostgreSQL service и locked uv cache.
Dependency audit зависит от доступности vulnerability feed. Findings не подавляйте молча:
обновите пакет либо документируйте ограниченное исключение с причиной и сроком.
GitHub Actions закреплены SHA; Dependabot обновляет их.
Gitleaks CLI скачивается из закреплённого release с проверкой SHA256 и не требует лицензии action.

## Production boundaries

`uv run uvicorn myapp.main:app --host 0.0.0.0 --no-proxy-headers` — процесс API.
Разрешайте forwarded headers только от явно заданных IP доверенного proxy.
Отдельный migration step: `uv run alembic upgrade head` с DDL ролью.
API runtime — без DDL, без superuser. Health доступен без токена; доступность docs можно
ограничить на внешнем proxy по политике проекта. SSO не является readiness dependency:
public endpoints продолжают работать, auth failures закрывают protected requests.

Audit cleanup удаляет старые записи порциями; при долгосрочном хранении сначала
добавьте архивирование и проверьте восстановление. PostgreSQL backup и rollback migration
требуют проектного плана; downgrade сам по себе не восстанавливает удалённые данные.
Перед внешним релизом возможен ручной OWASP ZAP scan в изолированном окружении.
