import json
import logging
import sys
from datetime import UTC, datetime

from myapp.core.config import Settings

SAFE_FIELDS = ("request_id", "method", "route", "status", "duration_ms", "exception_type")


class SafeFormatter(logging.Formatter):
    def __init__(self, production: bool):
        super().__init__()
        self.production = production

    def format(self, record: logging.LogRecord) -> str:
        event = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            **{name: getattr(record, name) for name in SAFE_FIELDS if hasattr(record, name)},
        }
        if self.production:
            return json.dumps(event, ensure_ascii=False)
        return " ".join(f"{key}={value}" for key, value in event.items())


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeFormatter(settings.environment == "production"))
    logger = logging.getLogger("myapp")
    logger.handlers = [handler]
    logger.setLevel(settings.logging.level)
    logger.propagate = False
    # HTTP clients otherwise emit URLs; access logging below uses normalized routes.
    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
