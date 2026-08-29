import os

import boto3
import pytest


AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://floci:4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-west-1")
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
