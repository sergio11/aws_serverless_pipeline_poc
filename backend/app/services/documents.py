from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.domain import Document, DocumentStatus


class DocumentNotFoundError(Exception):
    pass


class DocumentStore(Protocol):
    @property
    def bucket_name(self) -> str:
        pass

    def build_object_key(self, document_id: str, filename: str) -> str:
        pass

    def save(self, document: Document, content: str) -> None:
        pass

    def get(self, document_id: str) -> Document | None:
        pass

    def get_content(self, document_id: str) -> str | None:
        pass

    def publish_created(self, document_id: str) -> None:
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

    def get_content(self, document_id: str) -> str | None:
        return self._content.get(document_id)

    def publish_created(self, document_id: str) -> None:
        return None

    def build_object_key(self, document_id: str, filename: str) -> str:
        return f"documents/{document_id}/{filename}"

    @property
    def bucket_name(self) -> str:
        return self._bucket_name


class DocumentService:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def create_document(self, name: str, content: str) -> Document:
        document_id = uuid4().hex
        document = Document(
            id=document_id,
            name=name,
            bucket=self._store.bucket_name,
            object_key=self._store.build_object_key(document_id, name),
            size=len(content.encode("utf-8")),
            status=DocumentStatus.CREATED,
            created_at=datetime.now(UTC),
        )
        self._store.save(document, content)
        self._store.publish_created(document.id)
        return document

    def get_document(self, document_id: str) -> Document:
        document = self._store.get(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    def get_document_content(self, document_id: str) -> str:
        content = self._store.get_content(document_id)
        if content is None:
            raise DocumentNotFoundError(document_id)
        return content
