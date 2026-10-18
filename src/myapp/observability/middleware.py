import asyncio
import logging
import re
import time
from uuid import uuid4

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from myapp.audit.context import actor_id, request_id
from myapp.core.config import Settings
from myapp.core.exceptions import error_response


class RequestMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        candidate = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        rid = candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else uuid4().hex
        context = request_id.set(rid)
        actor_context = actor_id.set(None)
        started, status, sent = time.perf_counter(), 500, False

        async def wrapped_send(message: Message) -> None:
            nonlocal status, sent
            if message["type"] == "http.response.start":
                status, sent = message["status"], True
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", rid.encode()),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        try:
            # Buffer bounded input before calling the router so chunked requests obey the limit too.
            size, messages = 0, []
            async with asyncio.timeout(self.settings.request_timeout):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        raise ClientDisconnect()
                    size += len(message.get("body", b""))
                    if size > self.settings.max_request_bytes:
                        await error_response(413, "PAYLOAD_TOO_LARGE", "Request too large")(
                            scope, receive, wrapped_send
                        )
                        return
                    messages.append(message)
                    if not message.get("more_body", False):
                        break

                async def replay() -> Message:
                    return messages.pop(0) if messages else await receive()

                await self.app(scope, replay, wrapped_send)
        except TimeoutError:
            if not sent:
                await error_response(504, "REQUEST_TIMEOUT", "Request timed out")(
                    scope, receive, wrapped_send
                )
            else:
                raise
        except ClientDisconnect:
            status = 499
        except Exception as exc:
            logging.getLogger("myapp").error(
                "request_exception", extra={"request_id": rid, "exception_type": type(exc).__name__}
            )
            if not sent:
                await error_response(500, "INTERNAL_ERROR", "Internal server error")(
                    scope, receive, wrapped_send
                )
            else:
                raise
        finally:
            if self.settings.logging.access:
                route = scope.get("route")
                logging.getLogger("myapp").info(
                    "http_request",
                    extra={
                        "request_id": rid,
                        "method": scope["method"],
                        "route": getattr(route, "path", "<unmatched>"),
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                )
            request_id.reset(context)
            actor_id.reset(actor_context)
