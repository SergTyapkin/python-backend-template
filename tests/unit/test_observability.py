import asyncio
import json
import logging

from myapp.observability.logging import SafeFormatter


def test_json_logging_drops_sensitive_extras_and_traceback():
    record = logging.LogRecord("myapp", logging.ERROR, "file", 1, "request_exception", (), None)
    record.request_id = "safe-id"
    record.exception_type = "RuntimeError"
    record.authorization = "Bearer private-token"
    record.body = {"password": "private-password"}
    result = SafeFormatter(production=True).format(record)
    assert json.loads(result)["request_id"] == "safe-id"
    assert "private" not in result


async def test_request_id_isolation(app, client):
    from myapp.audit.context import request_id

    @app.get("/test/context")
    async def context():
        await asyncio.sleep(0.005)
        return {"requestId": request_id.get()}

    responses = await asyncio.gather(
        *[client.get("/test/context", headers={"X-Request-ID": f"request-{i}"}) for i in range(5)]
    )
    for index, response in enumerate(responses):
        assert response.json()["requestId"] == f"request-{index}"
        assert response.headers["x-request-id"] == f"request-{index}"
    response = await client.get("/test/context", headers={"X-Request-ID": "a" * 100})
    assert len(response.headers["x-request-id"]) == 32


async def test_cors_requires_explicit_origin(client):
    response = await client.options(
        "/health/live",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers
