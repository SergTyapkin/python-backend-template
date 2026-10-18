import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from myapp.audit.models import AuditLog
from myapp.core.config import Settings
from myapp.db.session import Database


async def cleanup_audit(settings: Settings, batch_size: int = 1000) -> int:
    database = Database(settings.database)
    cutoff = datetime.now(UTC) - timedelta(days=settings.audit.retention_days)
    count = 0
    try:
        async with database.sessions() as session:
            while True:
                async with session.begin():
                    ids = list(
                        await session.scalars(
                            select(AuditLog.id)
                            .where(AuditLog.timestamp < cutoff)
                            .order_by(AuditLog.timestamp)
                            .limit(batch_size)
                            .with_for_update(skip_locked=True)
                        )
                    )
                    if not ids:
                        break
                    await session.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
                    count += len(ids)
        return count
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone infrastructure jobs")
    parser.add_argument("job", choices=["audit-cleanup"])
    parser.parse_args()
    print(f"Removed audit rows: {asyncio.run(cleanup_audit(Settings()))}")
