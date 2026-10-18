# Команды

Кроссплатформенные реализации установлены как Python entry points в `src/myapp/cli.py`:
`uv run project-init`, `uv run project-migration "message"`, `uv run export-openapi`.
Standalone jobs: `uv run project-job audit-cleanup`. Bash/WSL не нужны.

`uv run python scripts/secret_scan.py --history` запускает Gitleaks по истории Git.
`--staged` проверяет только index. Первый запуск скачивает закреплённую версию CLI
в игнорируемую `.local/tools/` и проверяет SHA256 архива. CI использует `--history`.
