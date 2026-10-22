# Проверка версии 0.2 — 22 октября 2026

Windows, Python 3.14.6, PostgreSQL 18.3; отдельный временный кластер на 127.0.0.1:55439.
Существующая рабочая БД не использовалась. `.env` сохранён, реальный Git index не менялся.

- `uv sync --frozen`, `uv lock --check`: успешно; lock обновлён для SQLModel, Argon2, mypy/pre-commit.
- 60 тестов проходят: 51 unit, 9 PostgreSQL integration.
- Create required/default/factory, access modes, constraints и extra=forbid проверены.
- PATCH omission/null/non-nullable, отсутствие вызовов factory и итоговые межполевые правила проверены.
- Проверены ошибочные declarations/overrides, stable operationId/schema names, новое поле из одной декларации.
- Реальные owner-scoped list/total/retrieve/patch, 404 чужому пользователю, server-field injection — успешно.
- Argon2, hashed sessions, Secure/HttpOnly cookie, expiry/revocation, Origin, session-bound CSRF — успешно.
- Unique conflict 409 и rollback после flush вместе с audit — успешно.
- Отдельный тестовый Resource выполняет DELETE 204; Task DELETE отсутствует в маршрутах/OpenAPI.
- Проверена работа single-operation service override и custom handler с сохраняемой policy.
- Alembic empty-schema downgrade/upgrade, повторный upgrade и drift check — успешно (head 0002).
- Connection pool concurrency, separate sessions, cancellation/dispose и pagination query count — успешно.
- Запущен настоящий Uvicorn factory; scripts/example.py прошёл полный сценарий двух пользователей.
- Health/live, ready, version, docs, redoc, openapi.json вернули 200.
- Generated contract/env freshness, reproducibility при изменении runtime env — успешно.
- openapi-spec-validator, Ruff check/format, mypy, Bandit — успешно; wheel и sdist собраны.
- Gitleaks по всем изменениям через временный index: утечек нет. Detector не отключался;
  два false positives в тестовых паролях устранены заменой тестовых значений.
- pip-audit: исходный certifi 2026.10.18 имел PYSEC-2026-4320, lock обновлён до 2026.10.19;
  после обновления известных уязвимостей нет. Собственный локальный пакет не проверяется PyPI.
- Из контракта успешно сгенерированы TypeScript, Fetch SDK и Zod schemas, только в `.local/`.
  openapi-typescript 7.13.0, @hey-api/openapi-ts 0.99.0, совместимый TypeScript 5.9.3;
  без закреплённого TypeScript peer Hey API падал до чтения контракта, явная версия исправила запуск.

## Время hook

Настоящий `pre-commit run`, Windows, один staged Task Python-файл с небольшим изменением,
одинаковый код/зависимости во временной локальной копии репозитория. Выполнены оба hooks:
staged Ruff/files/secrets и полный быстрый generator/access набор; сети и БД не было.
Три успешных прогона: **8,913 / 7,968 / 7,704 с**, медиана **7,968 с**.
Первый прогон включает инициализацию local pre-commit cache. Это не performance assertion
и не сравнение с прежним Lefthook, где быстрые generator/access tests отсутствовали.

## Непроверенное и границы

GitHub Actions и Linux/macOS matrix подготовлены, но удалённо не запускались: push не выполнялся.
TypeScript/SDK/Zod generation проверена, браузерный frontend E2E здесь не создавался.
Реальный внешний SSO, email/reset/OAuth и opt-in AI workflow не вызывались.
Production deploy, нагрузочный стенд, rate limiter, backups и ZAP scan не реализованы.
CSRF recovery после потери токена требует повторного входа. Dynamic DTO не получают
автоматическую статическую типизацию полей mypy; custom services/schemas остаются явным escape hatch.
