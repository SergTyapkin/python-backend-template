# API conventions

- `/api/v1` — явно зарегистрированные ресурсы; GET, POST, PATCH, DELETE.
- Create обычно возвращает 201, delete — 204 без тела, update — Read DTO.
- JSON camelCase, Python/SQL snake_case. UUID strings, UTC timezone-aware ISO 8601.
- `Schema` запрещает неизвестные поля. Для секретов используйте отдельные входные DTO.
- PATCH: exclude_unset=True; отсутствие отличается от null. Проверяйте DB non-null invariants.
- List: items/total/limit/offset/hasNext; limit 1..100, offset 0..1000000.
- Фильтрация и сортировка подключаются явно. Whitelist columns, стабильный tie-breaker.
- Error: code/message/details/requestId. 400/401/403/404/409/422/429/500 и infrastructure 503/504.
- Validation input и stack traces не возвращаются. 401 содержит WWW-Authenticate: Bearer.
- X-Request-ID ограничен ASCII 1..64, иначе генерируется сервером; это correlation, не identity.
- Bearer JWT проверяется SSO verifier; scopes/permissions и ownership проверяются отдельно.
- Корреляцию можно принять извне; actor identity берётся только из проверенного principal.
- Запрос ограничен по времени и фактическому размеру тела, в том числе chunked.
- Streaming/large uploads требуют отдельного согласованного endpoint и storage pipeline:
  текущий middleware буферизует ограниченное тело. Response streaming ограничен общим timeout.
- CORS не является авторизацией. Credentials/cookie-auth не включены.
- Upstream proxy должен ограничивать headers/connections/rate; шаблон не содержит distributed limiter.

`uv run export-openapi --output .local/contracts/openapi.json` работает без подключения БД/SSO.
Frontend может генерировать TypeScript типы из этого артефакта своим инструментом.
Не добавляйте секреты/внутренние DTO в OpenAPI examples; ревью контракта обязательно.
