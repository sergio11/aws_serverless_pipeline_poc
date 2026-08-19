import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger("lambda-worker")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": logging.getLevelName(level),
        "service": "lambda-worker",
        "event": event,
        **fields,
    }
    logger.log(level, json.dumps(payload, default=str))


class DocumentStatus:
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WorkerSettings:
    aws_endpoint_url: str
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    dynamodb_table: str
    sqs_queue_name: str
    poll_interval_seconds: int

    @classmethod
    def from_environment(cls) -> "WorkerSettings":
        return cls(
            aws_endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
            aws_region=os.getenv("AWS_DEFAULT_REGION", "eu-west-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
            dynamodb_table=os.getenv("DYNAMODB_TABLE", "documents"),
            sqs_queue_name=os.getenv("SQS_QUEUE_NAME", "document-events"),
            poll_interval_seconds=int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2")),
        )


class DocumentProcessor:
    def __init__(self, s3_client: Any, dynamodb_resource: Any, table_name: str) -> None:
        self._s3 = s3_client
        self._table = dynamodb_resource.Table(table_name)

    def process(self, document_id: str) -> str:
        item = self._get_document(document_id)
        if item is None:
            log_event(logging.INFO, "document_missing", document_id=document_id)
            return "missing"

        if item.get("status") == DocumentStatus.PROCESSED:
            log_event(logging.INFO, "document_already_processed", document_id=document_id)
            return "skipped"

        self._update_status(document_id, DocumentStatus.PROCESSING)

        try:
            response = self._s3.get_object(Bucket=item["bucket"], Key=item["object_key"])
            content = response["Body"].read()
            processed_at = datetime.now(UTC).isoformat()
            self._table.update_item(
                Key={"id": document_id},
                UpdateExpression="SET #status = :status, #size = :size, processed_at = :processed_at",
                ExpressionAttributeNames={
                    "#status": "status",
                    "#size": "size",
                },
                ExpressionAttributeValues={
                    ":status": DocumentStatus.PROCESSED,
                    ":size": len(content),
                    ":processed_at": processed_at,
                },
            )
            log_event(logging.INFO, "document_processed", document_id=document_id, size=len(content))
            return "processed"
        except Exception as exc:
            self._update_status(document_id, DocumentStatus.FAILED)
            log_event(logging.ERROR, "document_processing_failed", document_id=document_id, reason=str(exc))
            raise

    def _get_document(self, document_id: str) -> dict[str, Any] | None:
        response = self._table.get_item(Key={"id": document_id})
        return response.get("Item")

    def _update_status(self, document_id: str, status: str) -> None:
        self._table.update_item(
            Key={"id": document_id},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": status},
        )


class SqsWorker:
    def __init__(self, sqs_client: Any, queue_name: str, processor: DocumentProcessor) -> None:
        self._sqs = sqs_client
        self._queue_name = queue_name
        self._processor = processor
        self._queue_url: str | None = None

    def run_once(self) -> int:
        try:
            response = self._sqs.receive_message(
                QueueUrl=self._get_queue_url(),
                MaxNumberOfMessages=10,
                WaitTimeSeconds=1,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {
                "AWS.SimpleQueueService.NonExistentQueue",
                "QueueDoesNotExist",
            }:
                self._queue_url = None
                log_event(logging.INFO, "queue_not_ready", queue_name=self._queue_name)
                return 0
            raise
        messages = response.get("Messages", [])

        processed_count = 0
        for message in messages:
            self._process_message(message)
            processed_count += 1

        return processed_count

    def _process_message(self, message: dict[str, Any]) -> None:
        try:
            payload = json.loads(message["Body"])
        except json.JSONDecodeError:
            log_event(logging.ERROR, "invalid_message", receipt_handle=message.get("ReceiptHandle"))
            self._delete_message(message)
            return

        if payload.get("event_type") != "DocumentCreated":
            log_event(logging.INFO, "unsupported_event", event_type=payload.get("event_type"))
            self._delete_message(message)
            return

        result = self._processor.process(payload["document_id"])
        log_event(logging.INFO, "message_processed", document_id=payload["document_id"], result=result)
        self._delete_message(message)

    def _delete_message(self, message: dict[str, Any]) -> None:
        self._sqs.delete_message(
            QueueUrl=self._get_queue_url(),
            ReceiptHandle=message["ReceiptHandle"],
        )

    def _get_queue_url(self) -> str:
        if self._queue_url is None:
            response = self._sqs.get_queue_url(QueueName=self._queue_name)
            self._queue_url = response["QueueUrl"]
        return self._queue_url


def create_processor(settings: WorkerSettings | None = None) -> DocumentProcessor:
    if settings is None:
        settings = WorkerSettings.from_environment()

    client_config = {
        "endpoint_url": settings.aws_endpoint_url,
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    return DocumentProcessor(
        s3_client=boto3.client("s3", **client_config),
        dynamodb_resource=boto3.resource("dynamodb", **client_config),
        table_name=settings.dynamodb_table,
    )


def build_worker(settings: WorkerSettings) -> SqsWorker:
    client_config = {
        "endpoint_url": settings.aws_endpoint_url,
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    return SqsWorker(
        sqs_client=boto3.client("sqs", **client_config),
        queue_name=settings.sqs_queue_name,
        processor=create_processor(settings),
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    processor = create_processor()
    results = []

    for record in event.get("Records", []):
        try:
            payload = json.loads(record["body"])
        except (json.JSONDecodeError, KeyError):
            log_event(logging.WARNING, "invalid_record")
            results.append({"error": "invalid_record"})
            continue

        if payload.get("event_type") == "DocumentCreated":
            result = processor.process(payload["document_id"])
            results.append({"document_id": payload["document_id"], "result": result})
        else:
            log_event(logging.INFO, "unsupported_event",
                      event_type=payload.get("event_type"))

    return {"processed": len([r for r in results if "result" in r]), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="Process a single SQS receive cycle and exit.")
    group.add_argument("--poll", action="store_true", help="Continuously poll SQS.")
    group.add_argument("--lambda-test", action="store_true",
                       help="Simulate a Lambda invocation for testing.")
    args = parser.parse_args()

    if args.lambda_test:
        test_event = {
            "Records": [{
                "body": json.dumps({
                    "event_type": "DocumentCreated",
                    "document_id": os.environ.get("TEST_DOCUMENT_ID", "test-doc")
                })
            }]
        }
        result = lambda_handler(test_event, None)
        print(json.dumps(result, indent=2))
        return

    settings = WorkerSettings.from_environment()
    worker = build_worker(settings)

    if args.once:
        count = worker.run_once()
        print(json.dumps({"processed_messages": count}))
        return

    while True:
        count = worker.run_once()
        print(json.dumps({"processed_messages": count}))
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
