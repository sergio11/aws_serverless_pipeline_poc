from fastapi.testclient import TestClient

from app.main import create_app
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


def test_rejects_empty_content() -> None:
    client = create_test_client()

    response = client.post("/documents", json={"name": "example.txt", "content": ""})

    assert response.status_code == 422
