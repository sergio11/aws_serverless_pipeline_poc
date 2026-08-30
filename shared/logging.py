import json
import logging
from datetime import UTC, datetime
from typing import Any


def create_log_event(service: str):
    logger = logging.getLogger(service)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def log_event(level: int, event: str, **fields: Any) -> None:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": logging.getLevelName(level),
            "service": service,
            "event": event,
            **fields,
        }
        logger.log(level, json.dumps(payload, default=str))

    return log_event
