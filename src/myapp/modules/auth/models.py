from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime

from myapp.resources.fields import ResourceModel, api_field


class LoginSession(ResourceModel, table=True):
    __tablename__ = "login_session"
    id: UUID = api_field(default_factory=uuid4, primary_key=True)
    user_id: UUID = api_field(foreign_key="app_user.id", index=True, ondelete="CASCADE")
    token_hash: str = api_field(max_length=64, unique=True)
    csrf_hash: str = api_field(max_length=64)
    expires_at: datetime = api_field(sa_type=DateTime(timezone=True), index=True)
