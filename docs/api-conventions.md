# Контракт и отдельный frontend

Generated `contracts/openapi.json` — единственный переносимый контракт. Редактируется Python,
затем выполняется `uv run export-openapi`; `--check` сравнивает байты, не пишет артефакт.
Экспорт использует declaration defaults и не требует DB/SSO/production secrets.
Установленный стек и контракт проверяются openapi-spec-validator, schemas — реальными запросами.

- snake_case JSON; UUID string/uuid; UTC aware ISO 8601/date-time.
- Create required/default и Patch omission/nullability выводятся из declaration.
- Patch non-nullable T можно опустить, но нельзя передать null; default не запускается.
- Error: code/message/details/request_id; validation input и stack trace не возвращаются.
- List: items/total/limit/offset. Limit 1..100, offset 0..1000000, стабильный id tie-breaker.
- Filter — точное равенство по allowlist; query типы/ограничения и sort enum опубликованы.
- Удаление принимает UUID в path, 204 без тела. У Task DELETE отсутствует.
- Cookie security scheme Session API key in cookie; login возвращает отдельный csrf_token.
- CSRF header X-CSRF-Token и строгий Origin проверяются для изменений; передавайте credentials.
- X-Request-ID — correlation, не identity. Ownership никогда не берётся из клиентского поля.

Во frontend репозитории можно использовать openapi-typescript для типов, openapi-fetch для
клиента, либо генератор клиента с runtime validation (например @hey-api/openapi-ts + zod).
Не копируйте модели вручную. Выберите версии генераторов в frontend lockfile и проверяйте diff
генерации в CI того репозитория. Здесь frontend/package.json не создаются.
Пример команды проверки TypeScript-типа: `npx openapi-typescript contracts/openapi.json -o types.d.ts`.
OpenAPI не описывает произвольные model validators и business policy; отрицательные запросы
и контрактные тесты нужны также с runtime validators. Типы не заменяют проверку ответа сервера.
`writeOnly` password существует только во входном Credentials, password_hash/server fields скрыты.
Для клиента cookie/CSRF стратегия настраивается отдельно от генерации функций HTTP.

Локально проверены openapi-typescript 7.13.0 и @hey-api/openapi-ts 0.99.0
(с совместимым TypeScript 5.9.3), включая plugins typescript/sdk/client-fetch/zod:

```sh
npx --yes openapi-typescript@7.13.0 contracts/openapi.json -o .local/contracts/types.d.ts
npx --yes --package=typescript@5.9.3 --package=@hey-api/openapi-ts@0.99.0 openapi-ts -i ./contracts/openapi.json -o .local/contracts/client -p @hey-api/typescript @hey-api/sdk @hey-api/client-fetch zod --no-log-file
```

Это только проверка генерации; Node dependencies не добавлены в backend.
В Zod TaskPatch.title сгенерирован как optional string без nullable, description — nullish.
Источник рекомендаций: [официальный CLI openapi-typescript](https://openapi-ts.dev/cli),
[официальные plugins Hey API](https://github.com/hey-api/openapi-typescript).
