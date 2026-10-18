from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
actor_id: ContextVar[str | None] = ContextVar("actor_id", default=None)
