import os
import time
from uuid import uuid4

import httpx2 as httpx


BACKEND_ENDPOINT = os.getenv("BACKEND_ENDPOINT", "http://backend:8000")


def test_document_workflow_reaches_processed_status() -> None:
    unique_name = f"e2e-{uuid4().hex}.txt"

    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{BACKEND_ENDPOINT}/documents",
            json={"name": unique_name, "content": "Hello E2E"},
        )
        assert response.status_code == 201
        created = response.json()

    document_id = created["id"]
    assert created["status"] == "created"

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        with httpx.Client(timeout=10) as client:
            read_response = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert read_response.status_code == 200
        document = read_response.json()
        if document["status"] == "processed":
            assert document["size"] == 9
            return
        time.sleep(1)

    raise AssertionError(f"Document {document_id} did not reach processed status")
