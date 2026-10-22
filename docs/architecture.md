# Архитектура и ограничения

`resources/` — небольшой поддерживаемый код шаблона, не сторонний framework.
ResourceModel наследует SQLModel и использует общую metadata с инфраструктурным audit ORM.
`api_field` передаёт SQLModel параметры БД, а access хранит в публичном FieldInfo metadata.
Генератор использует FieldInfo.asdict, create_model и обычные Pydantic defaults/JSON Schema hooks.
Исходные объявления не изменяются. Defaults Create валидируются; Patch factories очищаются.

Поле без access закрыто. Все generated Read поля сериализуются явным allowlist по column names.
Отношения и deferred columns не подгружаются через сериализацию. Read service отвергает unloaded поля.
Нет автоматических вложенных записей, cascade updates, recursive relation serializers или arbitrary SQL.

Resource требует table=True, один UUID primary key id, известные операции и явную policy.
По умолчанию сортируется id, любая другая сортировка дополняется id. Имена ресурсов/operationId
выводятся из статического path; не регистрируйте конфликтующие path/operationId в одном приложении.
Схемы создаются один раз на объявление ресурса, не на запрос. Custom схемы — явный escape hatch.
Дополнительные ограничения должны усиливать декларацию; неизвестные/противоречащие правила ошибочны.
Уникальность, FK и конкурентная целостность обеспечиваются БД, не только HTTP-валидацией.

## Policy / service / transactions

`Policy.authorize` по умолчанию запрещает операции. `scope` также запрещён по умолчанию.
TaskPolicy задаёт WHERE owner_id=current_user для списка, total и одной строки;
server_values выставляет owner_id только для Create. Клиентское поле не включено во входные DTO.
Отсутствующая и чужая строка дают 404. При PATCH/DELETE используется FOR UPDATE.
Для public ресурса явно передайте public policy и anonymous principal_dependency.
Для fully custom handler общая operation policy сохраняется, но handler обязан применять scope
к своим запросам. Дополнительный endpoint добавляйте обычным router, без дублирования стандартного.

Session dependency управляет begin/commit/rollback/close до отправки ответа. Service не commit.
TaskService переопределяет только create; пример можно заменить обычным Service без перестройки router.
Проверка итогового PATCH состояния выполняет model_validate на полном наборе колонок;
трансформирующие validators/сложные правила обновления требуют явного service override.
Известные integrity conflicts дают 409; SQL и параметры не выводятся клиенту/в лог.
Audit добавляет только явно публичные поля и изменения, учитывает exclusion/retention/size limit.

## Производительность и PostgreSQL

ORM objects — стандартный CRUD. Отдельные колонки нужны для измеренных тяжёлых запросов/аналитики.
Повторные SELECT на элемент списка означают возможный N+1: измерьте round trips и явно выберите
selectinload/joinedload. Не включайте eager loading автоматически для всех моделей.
Индекс добавляйте под частый WHERE/JOIN/ORDER BY, проверяя EXPLAIN и при необходимости
EXPLAIN (ANALYZE, BUFFERS) на представительном объёме. ANALYZE реально исполняет запрос:
изменения исследуйте в изолированной БД/транзакции с rollback. PRIMARY KEY/UNIQUE уже индексированы.
Лишние индексы стоят места и замедляют записи. Изменения индексов — отдельные ревью миграций.

Offset pagination сохраняет COUNT + LIMIT/OFFSET. При READ COMMITTED возможны разные snapshots;
строгий snapshot/дорогой COUNT/deep offset решаются в конкретном проекте после измерений.
Каждый worker имеет свой pool_size + max_overflow: учитывайте суммарный бюджет всех API/jobs.
Не разделяйте AsyncSession между concurrent tasks и не увеличивайте pool без измерений.

## Границы auth и будущих интеграций

Register/login — отдельные сценарии, User не имеет CRUD router. Пароль добавляется только в
Credentials поверх generated username schema; UserRead выводится из одной декларации User.
Пароль Argon2id, session token и CSRF token случайны, в БД хеши. Cookies HttpOnly/Secure/Lax.
Для cross-site фронтенда SameSite=None требует отдельного явного security design и HTTPS;
текущий шаблон рассчитан на same-site origins с разными портами/доверенными субдоменами.
Origin — точный allowlist, CORS credentials без wildcard. CSRF токен привязан к сессии.
CSRF восстановление после потери in-memory токена пока требует повторного входа.
Для внешнего SSO сохранены JWT/JWKS dependencies, но account linking/mapping не реализованы.

Email confirmation/reset: одноразовый случайный token, только hash в БД, короткий TTL, отзыв,
одинаковые ответы при неизвестном email, rate limits и отдельные транзакции/тесты.
OAuth: state, PKCE, nonce/issuer/audience, allowlist redirect URI, явное безопасное account linking.
Email provider, платежи, боты, WebSocket подключаются отдельными модулями через Depends/lifespan,
с timeout, идемпотентностью и fake/MockTransport в тестах. Рабочих интеграций здесь не заявлено.
CPU/hash работа выполняется в thread pool. Durable tasks, cron, backup, monitoring — внешние процессы;
встроенного scheduler в API нет. Существующая audit cleanup команда запускается только явно.

Использованные публичные API: [SQLModel](https://sqlmodel.tiangolo.com/tutorial/),
[Pydantic dynamic models](https://docs.pydantic.dev/latest/examples/dynamic_models/),
[Argon2 PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html).
CSRF/Origin основаны на [рекомендациях OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
