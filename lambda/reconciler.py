import argparse
import http.server
import json
import logging
import os
import signal
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("reconciler")
logging.basicConfig(level=logging.INFO, format="%(message)s")

_shutdown_event = threading.Event()


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


def _start_health_server(port: int = 8081) -> None:  # pragma: no cover
    server = http.server.HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": logging.getLevelName(level),
        "service": "reconciler",
        "event": event,
        **fields,
    }
    logger.log(level, json.dumps(payload, default=str))


def scan_stale_documents(table: Any, max_age_minutes: int) -> list[dict]:
    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
    stale: list[dict] = []
    last_key = None

    while True:
        kwargs: dict = {"FilterExpression": "#s = :created OR #s = :processing"}
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
        kwargs["ExpressionAttributeValues"] = {
            ":created": "created",
            ":processing": "processing",
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        response = table.scan(**kwargs)
        for item in response.get("Items", []):
            created_at = datetime.fromisoformat(item["created_at"]).astimezone(UTC)
            if created_at < cutoff:
                stale.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return stale


def send_requeue_message(sqs: Any, queue_url: str, document_id: str) -> None:
    message = {"event_type": "DocumentCreated", "document_id": document_id}
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message))
    log_event(logging.INFO, "document_requeued", document_id=document_id)


def reset_processing_lock(table: Any, document_id: str) -> bool:
    try:
        table.update_item(
            Key={"id": document_id},
            UpdateExpression="SET #s = :created REMOVE processing_owner, processing_started_at",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":created": "created"},
        )
        log_event(logging.INFO, "lock_reset", document_id=document_id)
        return True
    except Exception as exc:
        log_event(logging.WARNING, "lock_reset_failed",
                  document_id=document_id, reason=str(exc))
        return False


def run_reconciliation(config: dict, table_name: str, queue_name: str,
                       max_age_minutes: int) -> dict[str, Any]:
    dynamodb = boto3.resource("dynamodb", **config)
    sqs = boto3.client("sqs", **config)
    table = dynamodb.Table(table_name)

    try:
        queue_url = sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {
            "AWS.SimpleQueueService.NonExistentQueue",
            "QueueDoesNotExist",
        }:
            log_event(logging.ERROR, "queue_not_found", queue_name=queue_name)
            return {"reconciled": 0, "error": "queue_not_found"}
        raise

    log_event(logging.INFO, "scan_started", max_age_minutes=max_age_minutes)
    stale = scan_stale_documents(table, max_age_minutes)
    log_event(logging.INFO, "scan_completed", stale_count=len(stale))

    if not stale:
        return {"reconciled": 0}

    processed_count = 0
    for item in stale:
        doc_id = item["id"]
        status = item["status"]

        lock_reset = True
        if status == "processing":
            lock_reset = reset_processing_lock(table, doc_id)

        if lock_reset:
            send_requeue_message(sqs, queue_url, doc_id)
            processed_count += 1
        else:
            log_event(logging.WARNING, "requeue_skipped",
                      document_id=doc_id, reason="lock_reset_failed")

    log_event(logging.INFO, "reconciliation_complete",
              reconciled=processed_count, total=len(stale))
    return {"reconciled": processed_count, "total": len(stale)}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    config = {
        "endpoint_url": os.environ["AWS_ENDPOINT_URL"],
        "region_name": os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    }
    table_name = os.environ["DYNAMODB_TABLE"]
    queue_name = os.environ["SQS_QUEUE_NAME"]
    max_age_minutes = int(os.environ.get("RECONCILER_MAX_AGE_MINUTES", "10"))

    return run_reconciliation(config, table_name, queue_name, max_age_minutes)


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                        help="Run a single reconciliation cycle and exit.")
    parser.add_argument("--poll", action="store_true",
                        help="Run reconciliation periodically.")
    args = parser.parse_args()

    config = {
        "endpoint_url": os.environ["AWS_ENDPOINT_URL"],
        "region_name": os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    }
    table_name = os.environ["DYNAMODB_TABLE"]
    queue_name = os.environ["SQS_QUEUE_NAME"]
    max_age_minutes = int(os.environ.get("RECONCILER_MAX_AGE_MINUTES", "10"))
    poll_interval = int(os.environ.get("RECONCILER_POLL_INTERVAL_SECONDS", "300"))

    if args.once:
        result = run_reconciliation(config, table_name, queue_name, max_age_minutes)
        log_event(logging.INFO, "reconciliation_once", result=result)
        return

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    _start_health_server()
    log_event(logging.INFO, "worker_started", poll_interval=poll_interval)

    while not _shutdown_event.is_set():
        result = run_reconciliation(config, table_name, queue_name, max_age_minutes)
        log_event(logging.INFO, "reconciliation_cycle", result=result)
        _shutdown_event.wait(timeout=poll_interval)

    log_event(logging.INFO, "worker_stopped")


if __name__ == "__main__":  # pragma: no cover
    main()
