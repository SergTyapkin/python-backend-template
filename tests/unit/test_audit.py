from unittest.mock import AsyncMock, Mock

from myapp.audit.service import record_audit, sanitize
from myapp.core.config import AuditSettings


async def test_audit_redaction_and_size():
    session = Mock(flush=AsyncMock())
    settings = AuditSettings(max_payload_bytes=128)
    row = await record_audit(
        session,
        settings,
        action="update",
        entity_type="resource",
        entity_id="id",
        changes={"password": "s", "nested": {"token": "s"}, "name": "ok"},
    )
    assert row is not None and row.changes == {"nested": {}, "name": "ok"}
    assert not session.commit.called
    row = await record_audit(
        session,
        settings,
        action="update",
        entity_type="resource",
        entity_id="id",
        changes={"name": "a" * 1000},
    )
    assert row is not None and row.changes == {"truncated": True}
    settings.enabled = False
    assert (
        await record_audit(
            session, settings, action="delete", entity_type="resource", entity_id="id", changes={}
        )
        is None
    )
    assert sanitize({"blob": b"binary"}, set()) == {"blob": "[omitted]"}


async def test_audit_policy_and_camel_case_secrets():
    session = Mock(flush=AsyncMock())
    settings = AuditSettings()
    row = await record_audit(
        session,
        settings,
        action="update",
        entity_type="resource",
        entity_id="id",
        changes={"refreshToken": "s", "API-Key": "s", "privateField": "s", "changed": True},
        exclude={"private_field"},
    )
    assert row is not None and row.changes == {"changed": True}
    for action, entity_type in (("read", "resource"), ("update", "excluded")):
        settings.excluded_entities = {"excluded"}
        assert (
            await record_audit(
                session,
                settings,
                action=action,
                entity_type=entity_type,
                entity_id="id",
                changes={},
            )
            is None
        )
