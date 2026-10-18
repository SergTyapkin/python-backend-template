import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from myapp.audit.context import actor_id, request_id
from myapp.audit.models import AuditLog
from myapp.core.config import AuditSettings


def sanitize(value: Any, excluded: set[str], depth: int = 0) -> Any:
    if depth > 5:
        return "[omitted]"
    if isinstance(value, Mapping):
        return {
            str(k): sanitize(v, excluded, depth + 1)
            for k, v in value.items()
            if str(k).casefold().replace("-", "").replace("_", "") not in excluded
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(v, excluded, depth + 1) for v in value[:32]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:512]
    return "[omitted]"


async def record_audit(
    session: AsyncSession,
    settings: AuditSettings,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    changes: Mapping[str, Any],
    exclude: set[str] | None = None,
) -> AuditLog | None:
    if not settings.enabled or entity_type in settings.excluded_entities:
        return None
    if action not in settings.actions:
        return None
    excluded = {
        s.casefold().replace("-", "").replace("_", "")
        for s in AuditSettings().excluded_fields | settings.excluded_fields | (exclude or set())
    }
    payload = sanitize(changes, excluded)
    if (
        len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())
        > settings.max_payload_bytes
    ):
        payload = {"truncated": True}
    row = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=payload,
        actor_id=actor_id.get(),
        request_id=request_id.get(),
    )
    session.add(row)
    await session.flush()  # Never commit here: audit and business changes are atomic.
    return row
