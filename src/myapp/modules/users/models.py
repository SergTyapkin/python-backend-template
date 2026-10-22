from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime

from myapp.resources.fields import FieldAccess, ResourceModel, api_field


class User(ResourceModel, table=True):
    __tablename__ = "app_user"
    id: UUID = api_field(default_factory=uuid4, primary_key=True, access=FieldAccess.READ_ONLY)
    username: str = api_field(
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_.-]+$",
        unique=True,
        access=FieldAccess.READ_WRITE,
    )
    password_hash: str = api_field(max_length=512)
    created_at: datetime = api_field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )
