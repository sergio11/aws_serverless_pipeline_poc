from enum import StrEnum


class DocumentStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
