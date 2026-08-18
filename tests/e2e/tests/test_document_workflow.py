import os
import time
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
import httpx2 as httpx


BACKEND_ENDPOINT = os.getenv("BACKEND_ENDPOINT", "http://backend:8000")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://floci:4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-west-1")
S3_BUCKET = os.getenv("S3_BUCKET", "poc-local-documents")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "documents")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "document-events")
SQS_DLQ_NAME = os.getenv("SQS_DLQ_NAME", "document-events-dlq")


def aws_client_config() -> dict[str, str]:
    return {
        "endpoint_url": AWS_ENDPOINT_URL,
        "region_name": AWS_REGION,
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }


def test_document_workflow_reaches_processed_status() -> None:
    ensure_local_resources()
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

    assert_s3_object_exists(document_id, unique_name)
    assert_dynamodb_item_exists(document_id)

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


def assert_s3_object_exists(document_id: str, filename: str) -> None:
    s3 = boto3.client("s3", **aws_client_config())
    response = s3.get_object(
        Bucket=S3_BUCKET,
        Key=f"documents/{document_id}/{filename}",
    )
    assert response["Body"].read() == b"Hello E2E"


def assert_dynamodb_item_exists(document_id: str) -> None:
    dynamodb = boto3.client("dynamodb", **aws_client_config())
    response = dynamodb.get_item(
        TableName=DYNAMODB_TABLE,
        Key={"id": {"S": document_id}},
    )
    assert response["Item"]["id"]["S"] == document_id


def ensure_local_resources() -> None:
    s3 = boto3.client("s3", **aws_client_config())
    dynamodb = boto3.client("dynamodb", **aws_client_config())
    sqs = boto3.client("sqs", **aws_client_config())

    try:
        s3.create_bucket(
            Bucket=S3_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise

    try:
        dynamodb.create_table(
            TableName=DYNAMODB_TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceInUseException":
            raise

    dlq_url = sqs.create_queue(QueueName=SQS_DLQ_NAME)["QueueUrl"]
    dlq_attrs = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"]
    sqs.create_queue(
        QueueName=SQS_QUEUE_NAME,
        Attributes={
            "RedrivePolicy": '{"deadLetterTargetArn":"%s","maxReceiveCount":"3"}'
            % dlq_attrs["QueueArn"],
        },
    )
