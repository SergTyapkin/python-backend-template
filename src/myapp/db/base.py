from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def load_models() -> None:
    # Explicit imports are predictable; register future module models here.
    import myapp.audit.models  # noqa: F401
    import myapp.modules.auth.models  # noqa: F401
    import myapp.modules.tasks.models  # noqa: F401
    import myapp.modules.users.models  # noqa: F401
