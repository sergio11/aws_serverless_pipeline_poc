from datetime import UTC, datetime

from app.domain import Document, DocumentStatus
from app.services.documents import (
    DocumentInfrastructureError,
    DocumentNotFoundError,
    DocumentService,
    InMemoryDocumentStore,
)


def test_create_document的成功路径() -> None:
    store = InMemoryDocumentStore(bucket_name="test")
    service = DocumentService(store)

    doc = service.create_document("test.txt", "Hello")

    assert doc.name == "test.txt"
    assert doc.size == 5
    assert doc.status == DocumentStatus.CREATED


def test_create_document_cleans_up_on_publish_failure() -> None:
    class FailingPublishStore(InMemoryDocumentStore):
        def publish_created(self, document_id: str) -> None:
            raise RuntimeError("queue unavailable")

    store = FailingPublishStore(bucket_name="test")
    service = DocumentService(store)

    try:
        service.create_document("test.txt", "Hello")
        assert False, "Should have raised"
    except DocumentInfrastructureError:
        pass


def test_get_document_raises_infrastructure_error() -> None:
    class ErrorStore:
        bucket_name = "test"

        def build_object_key(self, document_id: str, filename: str) -> str:
            return f"docs/{document_id}/{filename}"

        def save(self, document: Document, content: str) -> None:
            pass

        def get(self, document_id: str) -> Document | None:
            raise RuntimeError("db down")

        def get_content(self, document_id: str) -> str | None:
            return None

        def publish_created(self, document_id: str) -> None:
            pass

        def delete(self, document_id: str) -> None:
            pass

    service = DocumentService(ErrorStore())

    try:
        service.get_document("doc-1")
        assert False, "Should have raised"
    except DocumentInfrastructureError as e:
        assert "metadata lookup failed" in str(e)


def test_get_document_content_raises_infrastructure_error() -> None:
    class ErrorStore:
        bucket_name = "test"

        def build_object_key(self, document_id: str, filename: str) -> str:
            return f"docs/{document_id}/{filename}"

        def save(self, document: Document, content: str) -> None:
            pass

        def get(self, document_id: str) -> Document | None:
            return Document(
                id=document_id,
                name="test.txt",
                bucket="test",
                object_key="docs/doc-1/test.txt",
                size=5,
                status=DocumentStatus.CREATED,
                created_at=datetime.now(UTC),
            )

        def get_content(self, document_id: str) -> str | None:
            raise RuntimeError("storage down")

        def publish_created(self, document_id: str) -> None:
            pass

        def delete(self, document_id: str) -> None:
            pass

    service = DocumentService(ErrorStore())

    try:
        service.get_document_content("doc-1")
        assert False, "Should have raised"
    except DocumentInfrastructureError as e:
        assert "content lookup failed" in str(e)


def test_get_document_content_raises_not_found_when_none() -> None:
    store = InMemoryDocumentStore(bucket_name="test")
    service = DocumentService(store)

    try:
        service.get_document_content("nonexistent")
        assert False, "Should have raised"
    except DocumentNotFoundError:
        pass


def test_delete_document() -> None:
    store = InMemoryDocumentStore(bucket_name="test")
    service = DocumentService(store)
    doc = service.create_document("test.txt", "Hello")

    service.delete_document(doc.id)

    try:
        service.get_document(doc.id)
        assert False, "Should have raised"
    except DocumentNotFoundError:
        pass


def test_delete_document_raises_not_found() -> None:
    store = InMemoryDocumentStore(bucket_name="test")
    service = DocumentService(store)

    try:
        service.delete_document("nonexistent")
        assert False, "Should have raised"
    except DocumentNotFoundError:
        pass


def test_delete_document_raises_infrastructure_error() -> None:
    class FailingDeleteStore:
        bucket_name = "test"

        def build_object_key(self, document_id: str, filename: str) -> str:
            return f"docs/{document_id}/{filename}"

        def save(self, document: Document, content: str) -> None:
            pass

        def get(self, document_id: str) -> Document | None:
            return Document(
                id=document_id,
                name="test.txt",
                bucket="test",
                object_key=f"docs/{document_id}/test.txt",
                size=5,
                status=DocumentStatus.CREATED,
                created_at=datetime.now(UTC),
            )

        def get_content(self, document_id: str) -> str | None:
            return None

        def publish_created(self, document_id: str) -> None:
            pass

        def delete(self, document_id: str) -> None:
            raise RuntimeError("delete failed")

    service = DocumentService(FailingDeleteStore())

    try:
        service.delete_document("doc-1")
        assert False, "Should have raised"
    except DocumentInfrastructureError as e:
        assert "deletion failed" in str(e)
