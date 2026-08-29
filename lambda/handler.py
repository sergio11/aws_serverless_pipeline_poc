import argparse
import http.server
import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

# SYNC: The log_event function below is duplicated in backend/app/logging.py
# Changes to log format must be applied to both files.

logger = logging.getLogger("lambda-worker")
logging.basicConfig(level=logging.INFO, format="%(message)s")

MAX_LOCK_AGE_SECONDS = int(os.getenv("MAX_LOCK_AGE_SECONDS", "300"))
_shutdown_event = threading.Event()


class DocumentNotFoundError(Exception):
    """Raised when a document_id references a non-existent DynamoDB item.

    This is a terminal error — the message will be retried by SQS and
    eventually moved to the DLQ after maxReceiveCount failures, because
    a missing document cannot become valid through retries.
    """


def _handle_signal(signum: int, frame: Any) -> None:  # pragma: no cover
    log_event(logging.INFO, "shutdown_signal_received", signal=signum)
    _shutdown_event.set()


class _HealthHandler(http.server.BaseHTTPRequestHandler):  # pragma: no cover
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _start_health_server(port: int = 8080) -> None:  # pragma: no cover
    server = http.server.HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": logging.getLevelName(level),
        "service": "lambda-worker",
        "event": event,
        **fields,
    }
    logger.log(level, json.dumps(payload, default=str))


# CRITICAL: This enum MUST stay synchronized with backend/app/domain.py:DocumentStatus.
# Both files define identical states. If adding new states, update BOTH files.
# The values must match exactly because they are stored in DynamoDB and compared
# across services. To verify synchronization, run:
#   diff <(python -c "from backend.app.domain import DocumentStatus; print(list(DocumentStatus))") \
#        <(python -c "import sys; sys.path.insert(0,'lambda'); from handler import DocumentStatus; print(list(DocumentStatus))")
class DocumentStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


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
    def from_environment(cls) -> "WorkerSettings":  # pragma: no cover
        return cls(
            aws_endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
            aws_region=os.getenv("AWS_DEFAULT_REGION", "eu-west-1"),
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            dynamodb_table=os.getenv("DYNAMODB_TABLE", "documents-metadata"),
            sqs_queue_name=os.getenv("SQS_QUEUE_NAME", "document-events"),
            poll_interval_seconds=int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2")),
        )


class DocumentProcessor:
    def __init__(self, s3_client: Any, dynamodb_resource: Any, table_name: str) -> None:
        self._s3 = s3_client
        self._table = dynamodb_resource.Table(table_name)

    def _resolve_owner(self) -> str:
        return os.environ.get("HOSTNAME") \
            or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") \
            or "lambda-worker"

    def process(self, document_id: str) -> str:
        item = self._get_document(document_id)
        if item is None:
            log_event(logging.WARNING, "document_missing", document_id=document_id)
            raise DocumentNotFoundError(
                f"Document {document_id} not found in DynamoDB"
            )

        if item.get("status") == DocumentStatus.PROCESSED:
            log_event(logging.INFO, "document_already_processed", document_id=document_id)
            return "skipped"

        if not self._acquire_processing_lock(document_id):
            log_event(logging.INFO, "document_being_processed_by_another_worker",
                      document_id=document_id)
            return "locked"

        try:
            self._update_status(document_id, DocumentStatus.PROCESSING)

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
            try:
                self._update_status(document_id, DocumentStatus.FAILED)
            except Exception:
                log_event(logging.ERROR, "failed_to_set_failed_status", document_id=document_id)
            log_event(logging.ERROR, "document_processing_failed", document_id=document_id, reason=str(exc))
            raise
        finally:
            self._release_processing_lock(document_id)

    def _acquire_processing_lock(self, document_id: str) -> bool:
        """Attempts to atomically acquire a processing lock."""
        item = self._get_document(document_id)
        if item is not None:
            existing_owner = item.get("processing_owner")
            if existing_owner:
                started_at = item.get("processing_started_at")
                if started_at:
                    lock_age = (datetime.now(UTC) - datetime.fromisoformat(started_at).astimezone(UTC)).total_seconds()
                    if lock_age > MAX_LOCK_AGE_SECONDS:
                        log_event(logging.WARNING, "lock_expired_releasing",
                                  document_id=document_id, lock_age=lock_age)
                        self._force_release_expired_lock(document_id)
                    else:
                        return False
                else:
                    return False

        try:
            self._table.update_item(
                Key={"id": document_id},
                UpdateExpression="SET processing_owner = :owner, processing_started_at = :started_at",
                ConditionExpression="attribute_not_exists(processing_owner) AND #status <> :processed",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":owner": self._resolve_owner(),
                    ":started_at": datetime.now(UTC).isoformat(),
                    ":processed": DocumentStatus.PROCESSED,
                },
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def _release_processing_lock(self, document_id: str) -> None:
        """Releases the processing lock only if the current owner."""
        try:
            self._table.update_item(
                Key={"id": document_id},
                UpdateExpression="REMOVE processing_owner, processing_started_at",
                ConditionExpression="processing_owner = :owner",
                ExpressionAttributeValues={
                    ":owner": self._resolve_owner(),
                },
            )
        except ClientError as exc:
            log_event(logging.WARNING, "lock_release_failed",
                      document_id=document_id, error=str(exc))

    def _force_release_expired_lock(self, document_id: str) -> None:
        """Force-releases an expired lock regardless of owner. Used when the
        original owner is presumed dead and another worker needs to recover."""
        try:
            self._table.update_item(
                Key={"id": document_id},
                UpdateExpression="REMOVE processing_owner, processing_started_at",
                ConditionExpression="attribute_exists(processing_owner)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return
            log_event(logging.WARNING, "force_lock_release_failed",
                      document_id=document_id, error=str(exc))

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

        try:
            result = self._processor.process(payload["document_id"])
        except Exception:
            log_event(logging.ERROR, "message_processing_failed",
                      document_id=payload["document_id"])
            return

        log_event(logging.INFO, "message_processed", document_id=payload["document_id"], result=result)

        if result == "locked":
            return

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


def create_processor(settings: WorkerSettings | None = None) -> DocumentProcessor:  # pragma: no cover
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


def build_worker(settings: WorkerSettings) -> SqsWorker:  # pragma: no cover
    client_config = {
        "endpoint_url": settings.aws_endpoint_url,
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    processor = DocumentProcessor(
        s3_client=boto3.client("s3", **client_config),
        dynamodb_resource=boto3.resource("dynamodb", **client_config),
        table_name=settings.dynamodb_table,
    )
    return SqsWorker(
        sqs_client=boto3.client("sqs", **client_config),
        queue_name=settings.sqs_queue_name,
        processor=processor,
    )


# Module-level processor for Lambda warm start reuse. Clients are created once
# and reused across invocations, avoiding connection overhead on warm starts.
_lambda_processor: DocumentProcessor | None = None


def _get_lambda_processor() -> DocumentProcessor:  # pragma: no cover
    global _lambda_processor
    if _lambda_processor is None:
        _lambda_processor = create_processor()
    return _lambda_processor


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    processor = _get_lambda_processor()
    results = []
    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")
        try:
            payload = json.loads(record["body"])
        except (json.JSONDecodeError, KeyError):
            log_event(logging.WARNING, "invalid_record", message_id=message_id)
            results.append({"error": "invalid_record"})
            batch_item_failures.append({"itemIdentifier": message_id})
            continue

        if payload.get("event_type") == "DocumentCreated":
            try:
                result = processor.process(payload["document_id"])
            except Exception as exc:
                log_event(logging.ERROR, "record_processing_failed",
                          document_id=payload["document_id"], reason=str(exc))
                results.append({"document_id": payload["document_id"], "error": str(exc)})
                batch_item_failures.append({"itemIdentifier": message_id})
                continue

            if result == "locked":
                log_event(logging.INFO, "record_deferred_locked",
                          document_id=payload["document_id"], message_id=message_id)
                results.append({"document_id": payload["document_id"], "result": result})
                batch_item_failures.append({"itemIdentifier": message_id})
                continue

            results.append({"document_id": payload["document_id"], "result": result})
        else:
            log_event(logging.INFO, "unsupported_event",
                      event_type=payload.get("event_type"))

    response: dict[str, Any] = {
        "processed": len([r for r in results if r.get("result") == "processed"]),
        "results": results,
    }
    if batch_item_failures:
        response["batchItemFailures"] = batch_item_failures
    return response


def _wait_for_endpoint(settings: WorkerSettings, retries: int = 30, delay: float = 2) -> None:  # pragma: no cover
    config = {
        "endpoint_url": settings.aws_endpoint_url,
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    sqs = boto3.client("sqs", **config)
    for attempt in range(1, retries + 1):
        try:
            sqs.get_queue_url(QueueName=settings.sqs_queue_name)
            log_event(logging.INFO, "endpoint_ready", attempt=attempt)
            return
        except EndpointConnectionError:
            log_event(logging.INFO, "waiting_for_endpoint", attempt=attempt, retries=retries)
            time.sleep(delay)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {
                "AWS.SimpleQueueService.NonExistentQueue",
                "QueueDoesNotExist",
            }:
                log_event(logging.INFO, "endpoint_ready", attempt=attempt)
                return
            raise
    log_event(logging.WARNING, "endpoint_not_ready_after_retries", retries=retries)


def main() -> None:  # pragma: no cover
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
        log_event(logging.INFO, "lambda_test_result", result=result)
        return

    settings = WorkerSettings.from_environment()

    _wait_for_endpoint(settings)

    worker = build_worker(settings)

    if args.once:
        count = worker.run_once()
        log_event(logging.INFO, "poll_cycle_once", processed_messages=count)
        return

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    _start_health_server()
    log_event(logging.INFO, "worker_started", poll_interval=settings.poll_interval_seconds)

    while not _shutdown_event.is_set():
        count = worker.run_once()
        log_event(logging.DEBUG, "poll_cycle", processed_messages=count)
        _shutdown_event.wait(timeout=settings.poll_interval_seconds)

    log_event(logging.INFO, "worker_stopped")


if __name__ == "__main__":  # pragma: no cover
    main()
