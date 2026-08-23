import json
import logging
from datetime import UTC, datetime
from typing import Any

# SYNC: This log_event function is duplicated in lambda/handler.py
# Changes must be applied to both files to maintain log format consistency.

logger = logging.getLogger("backend")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": logging.getLevelName(level),
        "service": "backend",
        "event": event,
        **fields,
    }
    logger.log(level, json.dumps(payload, default=str))
