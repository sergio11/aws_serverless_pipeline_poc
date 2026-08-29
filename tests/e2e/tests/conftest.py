import json
import os
import time

import boto3
import httpx
import pytest
from ulid import ULID


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
            response = sqs_client.receive_message(
                QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=2
            )
            messages = response.get("Messages", [])
            if not messages:
                break
            for msg in messages:
                sqs_client.delete_message(
                    QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"]
                )
    except Exception:
        pass


@pytest.fixture(autouse=True, scope="session")
def _clean_sqs():
    sqs = boto3.client("sqs", **_aws_config())
    _drain_queue(sqs, SQS_QUEUE_NAME)
    _drain_queue(sqs, SQS_DLQ_NAME)


@pytest.fixture(autouse=True, scope="session")
def _warm_up_lambda(_clean_sqs):
    """Force Lambda ESM to initialize by creating a document and waiting for processing.

    Floci's Lambda ESM has a cold start delay — it needs time to detect the
    EventSourceMapping, pull the Lambda Docker image, and start polling SQS.
    Without this warm-up, the first e2e tests that depend on Lambda processing
    will time out.
    """
    unique_name = f"warmup-{ULID()}.txt"
    document_id = None

    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{BACKEND_ENDPOINT}/documents",
            json={"name": unique_name, "content": "warmup"},
        )
        assert response.status_code == 201
        document_id = response.json()["id"]

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        with httpx.Client(timeout=10) as client:
            read_response = client.get(
                f"{BACKEND_ENDPOINT}/documents/{document_id}"
            )
        assert read_response.status_code == 200
        if read_response.json()["status"] == "processed":
            break
        time.sleep(2)
    else:
        pytest.fail(
            f"Warm-up document {document_id} did not reach processed status "
            "within 120s. Lambda ESM may not be functional."
        )

    s3 = boto3.client("s3", **_aws_config())
    object_key = f"documents/{document_id}/{unique_name}"
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=object_key)
    except Exception:
        pass

    dynamodb = boto3.resource("dynamodb", **_aws_config())
    table = dynamodb.Table(DYNAMODB_TABLE)
    try:
        table.delete_item(Key={"id": document_id})
    except Exception:
        pass

    _drain_queue(boto3.client("sqs", **_aws_config()), SQS_QUEUE_NAME)
