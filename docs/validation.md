# Локальная проверка шаблона

Проверено 18 октября 2026 года на Windows, Python 3.14.6 и PostgreSQL 18.3.
PostgreSQL запускался отдельным временным кластером на 127.0.0.1:55439;
существующая БД машины не использовалась. Временные файлы находятся в игнорируемой `.local/`.

- `uv sync --locked`: зависимости установлены из uv.lock.
- `project-init`: выполнен повторно; .env сохраняется, hooks установлены.
- Ruff check/format и Pyright: успешно.
- pytest: 39 passed, включая 3 PostgreSQL integration tests.
- JWT: проверены подпись, exp, issuer/audience, nbf, expected claims,
  permissions/ownership, JWKS cache/rotation и недоступность провайдера.
- Alembic: downgrade/upgrade на изолированной БД, повторный upgrade и check успешны;
  бизнес-таблиц нет, только audit_log и alembic_version.
- Аудит: commit/rollback, транзакция HTTP dependency, redaction, size limit и cleanup успешны.
- Uvicorn smoke: /health/live, /health/ready, /version, /docs, /redoc, /openapi.json — 200.
- Без SSO public endpoints работают; protected test endpoints закрыты.
- OpenAPI export и openapi-spec-validator: успешно.
- Lefthook pre-commit/pre-push: успешно на временном index, настоящий index не изменён.
- Bandit: замечаний нет; безопасные CLI subprocess имеют адресные исключения с объяснением.
- pip-audit: известных уязвимостей зависимостей не найдено; сам локальный пакет не проверяется PyPI.
- Gitleaks 8.30.1: просканированы все подготовленные файлы через временный index, утечек нет.
- Исходники не содержат demo entities, login/password APIs, PUT CRUD или create_all при старте.

GitHub Actions, Linux/macOS matrix и opt-in AI review подготовлены, но удалённо не запускались.
Реальный внешний SSO не подключался: JWT/JWKS проверены локальными ключами и HTTP mocks.
Production deployment и нагрузочные проверки не входят в шаблон. Git push не выполнялся.
