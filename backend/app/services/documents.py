import logging
from datetime import UTC, datetime
from typing import Protocol
from ulid import ULID

from app.domain import Document, DocumentStatus
from app.logging import log_event


class DocumentNotFoundError(Exception):
    pass


class DocumentInfrastructureError(Exception):
    pass


class DocumentStore(Protocol):
    @property
    def bucket_name(self) -> str:  # pragma: no cover
        pass

    def build_object_key(self, document_id: str, filename: str) -> str:  # pragma: no cover
        pass

    def save(self, document: Document, content: str) -> None:  # pragma: no cover
        pass

    def get(self, document_id: str) -> Document | None:  # pragma: no cover
        pass

    def get_content(self, document_id: str) -> bytes | None:  # pragma: no cover
        pass

    def delete(self, document_id: str) -> None:  # pragma: no cover
        pass

    def publish_created(self, document_id: str) -> None:  # pragma: no cover
        pass

    def health_check(self) -> dict[str, str]:  # pragma: no cover
        pass


class InMemoryDocumentStore:
    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._documents: dict[str, Document] = {}
        self._content: dict[str, str] = {}

    def save(self, document: Document, content: str) -> None:
        self._documents[document.id] = document
        self._content[document.id] = content

    def get(self, document_id: str) -> Document | None:
        return self._documents.get(document_id)

    def get_content(self, document_id: str) -> bytes | None:
        content = self._content.get(document_id)
        return content.encode("utf-8") if content is not None else None

    def delete(self, document_id: str) -> None:
        self._documents.pop(document_id, None)
        self._content.pop(document_id, None)

    def publish_created(self, document_id: str) -> None:
        return None

    def build_object_key(self, document_id: str, filename: str) -> str:
        return f"documents/{document_id}/{filename}"

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def health_check(self) -> dict[str, str]:
        return {"s3": "ok", "dynamodb": "ok", "sqs": "ok"}


class DocumentService:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def health_check(self) -> dict[str, str]:
        return self._store.health_check()

    def create_document(self, name: str, content: str) -> Document:
        document_id = str(ULID())
        document = Document(
            id=document_id,
            name=name,
            bucket=self._store.bucket_name,
            object_key=self._store.build_object_key(document_id, name),
            size=len(content.encode("utf-8")),
            status=DocumentStatus.CREATED,
            created_at=datetime.now(UTC),
        )
        saved = False
        try:
            self._store.save(document, content)
            saved = True
            self._store.publish_created(document.id)
        except Exception as exc:
            if saved:
                log_event(logging.ERROR, "create_document_failed",
                          document_id=document_id,
                          reason=str(exc),
                          note="SQS publish failed; attempting cleanup of saved document")
                try:
                    self._store.delete(document.id)
                except Exception:
                    log_event(logging.WARNING, "cleanup_failed_after_sqss_failure",
                              document_id=document_id)
            else:
                log_event(logging.ERROR, "create_document_failed",
                          document_id=document_id, reason=str(exc))
                try:
                    self._store.delete(document.id)
                except Exception:
                    log_event(logging.WARNING, "s3_cleanup_failed", document_id=document_id)
            raise DocumentInfrastructureError("document persistence failed") from exc
        return document

    def get_document(self, document_id: str) -> Document:
        try:
            document = self._store.get(document_id)
        except Exception as exc:
            raise DocumentInfrastructureError("document metadata lookup failed") from exc
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    def get_document_content(self, document_id: str) -> bytes:
        try:
            content = self._store.get_content(document_id)
        except Exception as exc:
            raise DocumentInfrastructureError("document content lookup failed") from exc
        if content is None:
            raise DocumentNotFoundError(document_id)
        return content

    def delete_document(self, document_id: str) -> None:
        try:
            document = self._store.get(document_id)
        except Exception as exc:
            raise DocumentInfrastructureError("document metadata lookup failed") from exc
        if document is None:
            raise DocumentNotFoundError(document_id)
        try:
            self._store.delete(document_id)
        except Exception as exc:
            raise DocumentInfrastructureError("document deletion failed") from exc
