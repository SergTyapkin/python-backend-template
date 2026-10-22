# Команды

- `uv run project-init`: идемпотентный bootstrap и установка единственного pre-commit hook.
- `uv run project-env [--check]`: generated .env.example из Pydantic settings.
- `uv run export-openapi [--check]`: generated contracts/openapi.json без runtime env/DB.
- `uv run project-migration "message"`: Alembic autogenerate с обязательным ручным ревью.
- `uv run python scripts/example.py`: полный сценарий локального API, без seed при импорте.
- `uv run python scripts/benchmark.py --help`: Ruff/mypy/pytest/pre-commit, health latency и pool checks.
- `uv run python scripts/secret_scan.py --staged`: pinned Gitleaks CLI, checksum-verified download
  в игнорируемую .local/tools. В CI используется --history, без коммерческой action-лицензии.
- `scripts/quick_tests.py` выбирает все test_resources*.py + access tests для resource изменений,
  для остальных изменений запускает небольшой unit-suite; вызывается pre-commit, без сети/БД.
- `uv run project-job audit-cleanup`: явная standalone cleanup-команда; встроенного scheduler нет.
