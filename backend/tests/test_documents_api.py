from datetime import UTC, datetime
from io import BytesIO

from fastapi.testclient import TestClient
from botocore.exceptions import ClientError

from app.main import create_app
from app.domain import Document, DocumentStatus
from app.services.documents import DocumentService, InMemoryDocumentStore


def create_test_client() -> TestClient:
    store = InMemoryDocumentStore(bucket_name="test-documents")
    return TestClient(create_app(document_service=DocumentService(store=store)))


def test_health_returns_ok() -> None:
    client = create_test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_read_document() -> None:
    client = create_test_client()

    create_response = client.post(
        "/documents",
        json={"name": "example.txt", "content": "Hello AWS"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "example.txt"
    assert created["status"] == "created"

    read_response = client.get(f"/documents/{created['id']}")

    assert read_response.status_code == 200
    assert read_response.json() == {
        "id": created["id"],
        "name": "example.txt",
        "size": 9,
        "status": "created",
    }


def test_get_document_content() -> None:
    client = create_test_client()
    create_response = client.post(
        "/documents",
        json={"name": "example.txt", "content": "Hello AWS"},
    )
    document_id = create_response.json()["id"]

    response = client.get(f"/documents/{document_id}/content")

    assert response.status_code == 200
    assert response.text == "Hello AWS"
    assert response.headers["content-type"].startswith("text/plain")


def test_unknown_document_returns_404() -> None:
    client = create_test_client()

    response = client.get("/documents/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_unknown_document_content_returns_404() -> None:
    client = create_test_client()

    response = client.get("/documents/missing/content")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_rejects_empty_content() -> None:
    client = create_test_client()

    response = client.post("/documents", json={"name": "example.txt", "content": ""})

    assert response.status_code == 422


class FailingDocumentStore:
    bucket_name = "failing-documents"

    def build_object_key(self, document_id: str, filename: str) -> str:
        return f"documents/{document_id}/{filename}"

    def save(self, document: Document, content: str) -> None:
        raise RuntimeError("storage unavailable")

    def get(self, document_id: str) -> Document | None:
        raise RuntimeError("database unavailable")

    def get_content(self, document_id: str) -> str | None:
        raise RuntimeError("storage unavailable")

    def publish_created(self, document_id: str) -> None:
        raise RuntimeError("queue unavailable")

    def delete(self, document_id: str) -> None:
        pass


def test_create_document_returns_500_when_infrastructure_fails() -> None:
    client = TestClient(create_app(document_service=DocumentService(store=FailingDocumentStore())))

    response = client.post(
        "/documents",
        json={"name": "example.txt", "content": "Hello AWS"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Document could not be created"}


def test_read_document_returns_500_when_infrastructure_fails() -> None:
    client = TestClient(create_app(document_service=DocumentService(store=FailingDocumentStore())))

    response = client.get("/documents/example")

    assert response.status_code == 500
    assert response.json() == {"detail": "Document could not be read"}


def test_content_returns_500_when_infrastructure_fails() -> None:
    client = TestClient(create_app(document_service=DocumentService(store=FailingDocumentStore())))

    response = client.get("/documents/example/content")

    assert response.status_code == 500
    assert response.json() == {"detail": "Document content could not be read"}
