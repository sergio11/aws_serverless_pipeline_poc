import json
import os
import time
from io import BytesIO
from ulid import ULID

import boto3
import pytest


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


class TestS3Integration:
    def test_put_and_get_object(self):
        s3 = boto3.client("s3", **_aws_config())
        key = f"integration-test/{ULID()}.txt"
        body = b"Hello Floci S3"

        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body, ContentType="text/plain")

        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        content = response["Body"].read()
        assert content == body

        s3.delete_object(Bucket=S3_BUCKET, Key=key)

    def test_get_nonexistent_object_returns_error(self):
        s3 = boto3.client("s3", **_aws_config())

        with pytest.raises(Exception) as exc_info:
            s3.get_object(Bucket=S3_BUCKET, Key="nonexistent/key.txt")
        assert exc_info.value.response["Error"]["Code"] in {"NoSuchKey", "404"}

    def test_put_and_list_objects(self):
        s3 = boto3.client("s3", **_aws_config())
        prefix = f"integration-test/{ULID()}/"
        key = f"{prefix}file.txt"

        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=b"list test", ContentType="text/plain")

        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        keys = [obj["Key"] for obj in response.get("Contents", [])]
        assert key in keys

        s3.delete_object(Bucket=S3_BUCKET, Key=key)


class TestDynamoDBIntegration:
    def test_put_and_get_item(self):
        dynamodb = boto3.resource("dynamodb", **_aws_config())
        table = dynamodb.Table(DYNAMODB_TABLE)
        item_id = f"integration-test-{ULID()}"

        table.put_item(Item={
            "id": item_id,
            "name": "test.txt",
            "bucket": S3_BUCKET,
            "object_key": f"docs/{item_id}/test.txt",
            "size": 9,
            "status": "created",
            "created_at": "2026-01-01T00:00:00+00:00",
        })

        response = table.get_item(Key={"id": item_id})
        assert response["Item"]["id"] == item_id
        assert response["Item"]["status"] == "created"
        assert response["Item"]["name"] == "test.txt"

        table.delete_item(Key={"id": item_id})

    def test_get_nonexistent_item_returns_empty(self):
        dynamodb = boto3.resource("dynamodb", **_aws_config())
        table = dynamodb.Table(DYNAMODB_TABLE)

        response = table.get_item(Key={"id": "nonexistent-id"})
        assert "Item" not in response

    def test_update_item_status(self):
        dynamodb = boto3.resource("dynamodb", **_aws_config())
        table = dynamodb.Table(DYNAMODB_TABLE)
        item_id = f"integration-test-{ULID()}"

        table.put_item(Item={
            "id": item_id,
            "name": "test.txt",
            "bucket": S3_BUCKET,
            "object_key": f"docs/{item_id}/test.txt",
            "size": 9,
            "status": "created",
            "created_at": "2026-01-01T00:00:00+00:00",
        })

        table.update_item(
            Key={"id": item_id},
            UpdateExpression="SET #status = :status, #size = :size, processed_at = :processed_at",
            ExpressionAttributeNames={"#status": "status", "#size": "size"},
            ExpressionAttributeValues={
                ":status": "processed",
                ":size": 18,
                ":processed_at": "2026-01-01T00:01:00+00:00",
            },
        )

        response = table.get_item(Key={"id": item_id})
        item = response["Item"]
        assert item["status"] == "processed"
        assert item["size"] == 18
        assert "processed_at" in item

        table.delete_item(Key={"id": item_id})


class TestSQSIntegration:
    def test_send_and_receive_message(self):
        sqs = boto3.client("sqs", **_aws_config())
        queue_url = sqs.get_queue_url(QueueName=SQS_QUEUE_NAME)["QueueUrl"]
        message_body = json.dumps({"event_type": "DocumentCreated", "document_id": "test-123"})

        sqs.send_message(QueueUrl=queue_url, MessageBody=message_body)

        response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=2)
        messages = response.get("Messages", [])
        assert len(messages) >= 1

        received_body = messages[0]["Body"]
        assert json.loads(received_body)["event_type"] == "DocumentCreated"

        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=messages[0]["ReceiptHandle"])

    def test_receive_empty_queue(self):
        sqs = boto3.client("sqs", **_aws_config())
        queue_url = sqs.get_queue_url(QueueName=SQS_QUEUE_NAME)["QueueUrl"]

        response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=1)
        assert response.get("Messages", []) == []

    def test_send_multiple_and_delete_all(self):
        sqs = boto3.client("sqs", **_aws_config())
        queue_url = sqs.get_queue_url(QueueName=SQS_QUEUE_NAME)["QueueUrl"]

        for i in range(3):
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps({"event_type": "DocumentCreated", "document_id": f"doc-{i}"}),
            )

        response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=2)
        messages = response.get("Messages", [])
        assert len(messages) >= 3

        for msg in messages:
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])

        response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
        assert response.get("Messages", []) == []

    def test_dlq_is_empty(self):
        sqs = boto3.client("sqs", **_aws_config())
        dlq_url = sqs.get_queue_url(QueueName=SQS_DLQ_NAME)["QueueUrl"]

        response = sqs.receive_message(QueueUrl=dlq_url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
        assert response.get("Messages", []) == []

    def test_dlq_redrive(self):
        """Verify messages that fail processing land in the DLQ.

        Sends a message with a non-existent document_id to the main queue.
        The worker should fail to process it and, after retries, the message
        should land in the DLQ.
        """
        sqs = boto3.client("sqs", **_aws_config())

        dlq_url = sqs.get_queue_url(QueueName=SQS_DLQ_NAME)["QueueUrl"]
        assert dlq_url

        queue_url = sqs.get_queue_url(QueueName=SQS_QUEUE_NAME)["QueueUrl"]
        queue_attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["RedrivePolicy"]
        )
        redrive_policy = json.loads(queue_attrs["Attributes"]["RedrivePolicy"])
        assert redrive_policy["deadLetterTargetArn"]

        invalid_doc_id = f"nonexistent-{ULID()}"
        message_body = json.dumps({
            "event_type": "DocumentCreated",
            "document_id": invalid_doc_id,
        })
        sqs.send_message(QueueUrl=queue_url, MessageBody=message_body)

        deadline = time.monotonic() + 60
        dlq_message_found = False
        while time.monotonic() < deadline:
            response = sqs.receive_message(
                QueueUrl=dlq_url, MaxNumberOfMessages=10, WaitTimeSeconds=5
            )
            messages = response.get("Messages", [])
            for msg in messages:
                body = json.loads(msg["Body"])
                if body.get("document_id") == invalid_doc_id:
                    dlq_message_found = True
                    break
            if dlq_message_found:
                break

        assert dlq_message_found, (
            f"Message with document_id={invalid_doc_id} did not land in DLQ within timeout"
        )
