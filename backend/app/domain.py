from dataclasses import dataclass
from datetime import datetime

from shared.domain import DocumentStatus


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    bucket: str
    object_key: str
    size: int
    status: DocumentStatus
    created_at: datetime
    processed_at: datetime | None = None
