import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from ulid import ULID

import boto3
import httpx
import pytest


BACKEND_ENDPOINT = os.getenv("BACKEND_ENDPOINT", "http://backend:8000")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://floci:4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-west-1")
S3_BUCKET = os.getenv("S3_BUCKET", "poc-local-documents")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "poc-local-documents-metadata")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "poc-local-document-events")
SQS_DLQ_NAME = os.getenv("SQS_DLQ_NAME", "poc-local-document-events-dlq")


def _aws_config():
    return {
        "endpoint_url": AWS_ENDPOINT_URL,
        "region_name": AWS_REGION,
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }


def _drain_queue(sqs_client, queue_name):
    try:
        url = sqs_client.get_queue_url(QueueName=queue_name)["QueueUrl"]
        while True:
            response = sqs_client.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=2)
            messages = response.get("Messages", [])
            if not messages:
                break
            for msg in messages:
                sqs_client.delete_message(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"])
    except Exception:
        pass


@pytest.fixture(autouse=True, scope="session")
def _clean_sqs():
    sqs = boto3.client("sqs", **_aws_config())
    _drain_queue(sqs, SQS_QUEUE_NAME)
    _drain_queue(sqs, SQS_DLQ_NAME)


def test_document_workflow_reaches_processed_status() -> None:
    """Verify the full document lifecycle: POST -> S3 -> DynamoDB -> SQS -> Lambda -> PROCESSED.

    Processing is asynchronous via Lambda (Floci-managed). This test polls the
    backend until the document reaches PROCESSED status, then validates
    S3 content, DynamoDB metadata, and SQS state.
    """
    unique_name = f"e2e-{ULID()}.txt"
    content = "Hello E2E"

    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{BACKEND_ENDPOINT}/documents",
            json={"name": unique_name, "content": content},
        )
        assert response.status_code == 201
        created = response.json()

    document_id = created["id"]
    assert created["status"] == "created"

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with httpx.Client(timeout=10) as client:
            read_response = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert read_response.status_code == 200
        document = read_response.json()
        if document["status"] == "processed":
            assert document["size"] == 9
            break
        time.sleep(1)
    else:
        pytest.fail(
            f"Document {document_id} did not reach processed status within 45s. "
            "Lambda ESM may not be functional (e.g. Podman without Docker socket)."
        )

    s3 = boto3.client("s3", **_aws_config())
    object_key = f"documents/{document_id}/{unique_name}"
    s3_response = s3.get_object(Bucket=S3_BUCKET, Key=object_key)
    s3_content = s3_response["Body"].read().decode("utf-8")
    assert s3_content == content

    dynamodb = boto3.resource("dynamodb", **_aws_config())
    table = dynamodb.Table(DYNAMODB_TABLE)
    db_response = table.get_item(Key={"id": document_id})
    db_item = db_response["Item"]
    assert db_item["id"] == document_id
    assert db_item["name"] == unique_name
    assert db_item["status"] == "processed"
    assert db_item["bucket"] == S3_BUCKET
    assert db_item["object_key"] == object_key
    assert db_item["size"] == 9
    assert "created_at" in db_item
    assert "processed_at" in db_item

    sqs = boto3.client("sqs", **_aws_config())
    dlq_url = sqs.get_queue_url(QueueName=SQS_DLQ_NAME)["QueueUrl"]
    dlq_response = sqs.receive_message(QueueUrl=dlq_url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
    assert dlq_response.get("Messages", []) == [], "DLQ should be empty after successful processing"

    queue_url = sqs.get_queue_url(QueueName=SQS_QUEUE_NAME)["QueueUrl"]
    queue_response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
    remaining = queue_response.get("Messages", [])
    assert remaining == [], "Main queue should be empty after processing"


def test_lambda_function_exists() -> None:
    """Verify the Lambda function is registered in Floci."""
    lambda_client = boto3.client("lambda", **_aws_config())
    response = lambda_client.get_function(FunctionName="poc-local-document-processor")
    assert response["Configuration"]["FunctionName"] == "poc-local-document-processor"


def test_document_delete_workflow() -> None:
    """Verify document can be deleted via DELETE /documents/{id}.

    Creates a document, confirms it exists via GET, deletes it, then confirms
    the deletion by verifying GET returns 404 and a second DELETE also returns 404.
    """
    unique_name = f"e2e-delete-{ULID()}.txt"
    content = "Delete me"

    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{BACKEND_ENDPOINT}/documents",
            json={"name": unique_name, "content": content},
        )
        assert response.status_code == 201
        created = response.json()

    document_id = created["id"]

    with httpx.Client(timeout=10) as client:
        get_response = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert get_response.status_code == 200

    with httpx.Client(timeout=10) as client:
        delete_response = client.delete(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert delete_response.status_code == 204

    with httpx.Client(timeout=10) as client:
        get_after_delete = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert get_after_delete.status_code == 404

    with httpx.Client(timeout=10) as client:
        delete_again = client.delete(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert delete_again.status_code == 404


def _create_document_and_wait_processed(client: httpx.Client, name: str, content: str) -> str:
    response = client.post(
        f"{BACKEND_ENDPOINT}/documents",
        json={"name": name, "content": content},
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        read_response = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert read_response.status_code == 200
        if read_response.json()["status"] == "processed":
            return document_id
        time.sleep(1)
    pytest.fail(f"Document {document_id} did not reach processed status within 45s")


def test_document_content_retrieval() -> None:
    """Verify GET /documents/{id}/content returns the original bytes after processing."""
    unique_name = f"e2e-content-{ULID()}.txt"
    content = "Content retrieval test"

    with httpx.Client(timeout=10) as client:
        document_id = _create_document_and_wait_processed(client, unique_name, content)

        response = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}/content")
        assert response.status_code == 200
        assert response.text == content
        assert "text/plain" in response.headers["content-type"]


def test_document_content_nonexistent_returns_404() -> None:
    """Verify GET /documents/{id}/content returns 404 for unknown documents."""
    with httpx.Client(timeout=10) as client:
        response = client.get(f"{BACKEND_ENDPOINT}/documents/nonexistent-doc-000/content")
        assert response.status_code == 404


def test_document_failed_status() -> None:
    """Verify a document that fails Lambda processing reaches failed status.

    Creates a document, then deletes its S3 object before Lambda processes it.
    Lambda will fail on get_object, setting status=failed in DynamoDB.
    """
    unique_name = f"e2e-failed-{ULID()}.txt"
    content = "Will fail"

    s3 = boto3.client("s3", **_aws_config())

    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{BACKEND_ENDPOINT}/documents",
            json={"name": unique_name, "content": content},
        )
        assert response.status_code == 201
        document_id = response.json()["id"]

    object_key = f"documents/{document_id}/{unique_name}"
    s3.delete_object(Bucket=S3_BUCKET, Key=object_key)

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with httpx.Client(timeout=10) as client:
            read_response = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert read_response.status_code == 200
        doc = read_response.json()
        if doc["status"] == "failed":
            break
        time.sleep(1)
    else:
        pytest.fail(f"Document {document_id} did not reach failed status within 45s")

    dynamodb = boto3.resource("dynamodb", **_aws_config())
    table = dynamodb.Table(DYNAMODB_TABLE)
    db_item = table.get_item(Key={"id": document_id})["Item"]
    assert db_item["status"] == "failed"
    assert "processed_at" not in db_item


def test_get_nonexistent_document_returns_404() -> None:
    """Verify GET /documents/{id} returns 404 for unknown documents."""
    with httpx.Client(timeout=10) as client:
        response = client.get(f"{BACKEND_ENDPOINT}/documents/nonexistent-doc-000")
        assert response.status_code == 404


def test_delete_nonexistent_document_returns_404() -> None:
    """Verify DELETE /documents/{id} returns 404 for unknown documents."""
    with httpx.Client(timeout=10) as client:
        response = client.delete(f"{BACKEND_ENDPOINT}/documents/nonexistent-doc-000")
        assert response.status_code == 404


def test_create_document_with_invalid_payload_returns_422() -> None:
    """Verify POST /documents rejects invalid payloads."""
    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{BACKEND_ENDPOINT}/documents",
            json={"name": "", "content": ""},
        )
        assert response.status_code == 422

        response = client.post(
            f"{BACKEND_ENDPOINT}/documents",
            json={"name": "x" * 256, "content": "ok"},
        )
        assert response.status_code == 422


def test_health_and_readiness_endpoints() -> None:
    """Verify /health and /ready endpoints respond correctly."""
    with httpx.Client(timeout=10) as client:
        health = client.get(f"{BACKEND_ENDPOINT}/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        ready = client.get(f"{BACKEND_ENDPOINT}/ready")
        assert ready.status_code == 200
        body = ready.json()
        assert body["status"] == "ok"
        assert "dependencies" in body


def test_reconciler_recovery_of_stale_document() -> None:
    """Verify the reconciler recovers a document stuck in created state.

    Creates a document, waits for processing, then directly sets DynamoDB
    status back to 'created' with an old timestamp. Calls the reconciler
    to requeue it, then verifies Lambda reprocesses it to 'processed'.
    """
    sys.path.insert(0, "/app/lambda")
    from reconciler import run_reconciliation

    unique_name = f"e2e-reconcile-{ULID()}.txt"
    content = "Reconcile me"

    with httpx.Client(timeout=10) as client:
        document_id = _create_document_and_wait_processed(client, unique_name, content)

    dynamodb = boto3.resource("dynamodb", **_aws_config())
    table = dynamodb.Table(DYNAMODB_TABLE)
    stale_time = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
    table.update_item(
        Key={"id": document_id},
        UpdateExpression="SET #s = :created, created_at = :ts REMOVE processed_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":created": "created", ":ts": stale_time},
    )

    config = {
        "endpoint_url": AWS_ENDPOINT_URL,
        "region_name": AWS_REGION,
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }
    result = run_reconciliation(config, DYNAMODB_TABLE, SQS_QUEUE_NAME, max_age_minutes=10)
    assert result["reconciled"] == 1

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with httpx.Client(timeout=10) as client:
            read_response = client.get(f"{BACKEND_ENDPOINT}/documents/{document_id}")
        assert read_response.status_code == 200
        if read_response.json()["status"] == "processed":
            break
        time.sleep(1)
    else:
        pytest.fail(f"Document {document_id} was not reprocessed after reconciliation")
