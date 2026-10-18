from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import AwareDatetime, ValidationError

from myapp.api.pagination import Page, Pagination
from myapp.api.responses import Schema
from myapp.core.config import AuthSettings
from tests.settings import IsolatedSettings


class ReadSchema(Schema):
    record_id: UUID
    created_at: AwareDatetime
    description: str | None = None


class PatchSchema(Schema):
    display_name: str | None = None


def test_serialization():
    item = ReadSchema(record_id=uuid4(), created_at=datetime.now(UTC))
    data = item.model_dump(mode="json", by_alias=True)
    assert data["recordId"] == str(item.record_id)
    assert data["createdAt"].endswith("Z")
    assert data["description"] is None
    with pytest.raises(ValidationError):
        ReadSchema(record_id=uuid4(), created_at=datetime(2026, 1, 1))


def test_patch_distinguishes_absent_and_null():
    assert PatchSchema().model_dump(exclude_unset=True) == {}
    assert PatchSchema.model_validate({"displayName": None}).model_dump(exclude_unset=True) == {
        "display_name": None
    }
    assert PatchSchema.model_validate({"displayName": "new"}).model_dump(exclude_unset=True) == {
        "display_name": "new"
    }


def test_pagination():
    assert Pagination().limit == 20
    for values in ({"limit": 101}, {"offset": -1}, {"limit": 0}):
        with pytest.raises(ValidationError):
            Pagination(**values)
    page = Page[int](items=[1], total=2, limit=1, offset=0)
    assert page.model_dump(by_alias=True)["hasNext"] is True
    assert Page[int](items=[], total=0, limit=20, offset=0).has_next is False


def test_safe_config():
    with pytest.raises(ValidationError):
        IsolatedSettings(cors_origins=["*"])
    with pytest.raises(ValidationError):
        IsolatedSettings(environment="production")
    with pytest.raises(ValidationError):
        AuthSettings(issuer="https://sso.example")
    with pytest.raises(ValidationError):
        AuthSettings(issuer="http://sso.example", audience="api")
