from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DocumentStatus(StrEnum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    bucket: str
    object_key: str
    size: int
    status: str
    created_at: datetime
    processed_at: datetime | None = None
