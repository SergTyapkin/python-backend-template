from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, UniqueConstraint

from myapp.resources import FieldAccess, ResourceModel, api_field


class Task(ResourceModel, table=True):
    __tablename__ = "task"
    __table_args__ = (UniqueConstraint("owner_id", "title", name="uq_task_owner_title"),)
    id: UUID = api_field(default_factory=uuid4, primary_key=True, access=FieldAccess.READ_ONLY)
    title: str = api_field(
        min_length=1,
        max_length=200,
        access=FieldAccess.READ_WRITE,
        description="Task title, unique per owner",
    )
    description: str | None = api_field(
        default=None, max_length=5000, access=FieldAccess.READ_WRITE
    )
    # UNIQUE(owner_id, title) already indexes its owner_id prefix.
    owner_id: UUID = api_field(foreign_key="app_user.id")
    created_at: datetime = api_field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        access=FieldAccess.READ_ONLY,
    )
