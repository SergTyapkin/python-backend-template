# Разработка и проверки

Зависимости: `uv sync --frozen`; обновления — `uv lock --upgrade` с ревью diff/CI.
Версии Python 3.14 и SQLModel/Pydantic закреплены, фабрика использует публичные API установленной версии.
Импорт main не создаёт приложение, файлы или соединения: запускайте create_app через --factory.

Миграции: `uv run project-migration "message"`, ревью, `uv run alembic upgrade head`,
`uv run alembic check`. Autogenerate не гарантирует правильное rename/data migration.
Не запускайте downgrade на рабочей БД. Runtime role без DDL, migration role отдельно в будущем.
Audit 0001 сохранён, 0002 добавляет app_user/login_session/task без демонстрационных seed данных.

## Отдельная PostgreSQL для integration

Создайте отдельную БД app_test. Тесты удаляют/пересоздают схему и очищают данные.
Проверяется суффикс _test, но он не заменяет правильный выбор URL.

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/app_test'
uv run pytest tests/integration -q
```

```sh
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q
```

Без URL integration явно skipped. SQLite не заменяет PostgreSQL. Alembic downgrade/upgrade,
повторный upgrade и metadata drift проверяются fixture/тестами один раз за прогон.
Между тестами очищаются audit/task/session/user, engine закрывается в finally.
Task ownership, total, CSRF, expiry/logout, unique conflict и atomic rollback проверяются через HTTPX.

## Только pre-commit

`uv run project-init` идемпотентно устанавливает pre-commit; старые Lefthook hooks удаляются
только при обнаружении их маркера. Нет pre-push hook и параллельной второй системы.
Существующий чужой hook pre-commit не удаляется вручную; pre-commit управляет своей установкой.
Для ручной проверки: `uv run pre-commit run --all-files` (проверяет индексные версии файлов).

Первый local hook запускает Ruff check/format параллельно по изменённым Python-файлам,
на временному снимке index, и лёгкий config/secret check по тем же blobs. Рабочая копия
не подменяет staged версии; поддержаны пробелы в именах. Configs pyproject.toml/ruff.toml/.ruff.toml
также берутся из index. Для custom extend с другим именем дополните RUFF_CONFIG_FILES.
Второй hook всегда запускает все test_resources.py и access tests для генератора/Task;
при остальных изменениях выполняет полный небольшой unit-suite. pre-commit скрывает
unstaged изменения на время запуска. Файлы не форматируются автоматически и index не меняется.
Исправляйте Ruff отдельно и повторно git add. Нет uv sync, сети, integration, type check или AI в hook.

CI: frozen uv sync + cache, Ruff, mypy, unit, независимый PostgreSQL job, migrations/drift,
env/contract freshness, Python build, pip-audit/Bandit, pinned checksum Gitleaks.
Права contents:read, PR код не получает production secrets. Dependabot package-ecosystem uv
поддерживает pyproject.toml и uv.lock; github-actions обновляет закреплённые SHA.

[Поддержка uv в Dependabot](https://docs.astral.sh/uv/guides/integration/dependabot/)
проверена по официальной документации uv.

## Измерения и opt-in

```sh
uv run python scripts/benchmark.py --checks ruff mypy unit integration pool
uv run python scripts/benchmark.py --checks pre-commit --repeat 3
uv run python scripts/benchmark.py --checks health --base-url http://localhost:8000 --samples 50
```

Отчёт .local/benchmark.json включает wall-clock/exit codes и health p50/p95 после прогрева.
Для integration/pool нужен TEST_DATABASE_URL, для health — запущенный API; иначе явный skip.
Не сравнивайте разные staged-наборы, холодные/прогретые запуски и параллельную нагрузку.
Нет speed assertions. Текущие результаты и непроверенные части — docs/validation.md.

AI review выключен: ENABLE_AI_REVIEW=true, AI_REVIEW_MODEL, AI_REVIEW_API_KEY и manual workflow
включаются владельцем отдельно. Diff уходит провайдеру, результат advisory summary, PR код
не исполняется с секретом. ZAP — будущий ручной scan изолированного стенда, deployment здесь нет.
