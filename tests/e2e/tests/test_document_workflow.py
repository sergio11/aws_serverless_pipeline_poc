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
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "documents-metadata")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "document-events")
SQS_DLQ_NAME = os.getenv("SQS_DLQ_NAME", "document-events-dlq")


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
