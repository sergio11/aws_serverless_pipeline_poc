import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from conftest import (
    FakeDynamoResource,
    FakeS3Client,
    FakeSqsClient,
    FakeTable,
    make_queue_does_not_exist_error,
)
from handler import DocumentProcessor, DocumentStatus, SqsWorker


def test_processor_marks_document_processed() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "processed"
    assert item["status"] == DocumentStatus.PROCESSED
    assert item["size"] == 9
    assert "processed_at" in item


def test_processor_skips_already_processed_document() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "processed",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "skipped"
    assert table.updates == []


def test_processor_returns_missing_for_nonexistent_document() -> None:
    table = FakeTable(None)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-missing")

    assert result == "missing"
    assert table.updates == []


def test_processor_attempts_reprocess_on_failed_document() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "failed",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "processed"
    assert item["status"] == DocumentStatus.PROCESSED


def test_processor_attempts_reprocess_on_processing_document() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "processing",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "processed"
    assert item["status"] == DocumentStatus.PROCESSED


def test_processor_marks_failed_on_s3_error() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    s3 = FakeS3Client()
    s3.fail_with(ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject"))
    processor = DocumentProcessor(s3, FakeDynamoResource(table), "documents")

    with pytest.raises(ClientError):
        processor.process("doc-1")

    assert item["status"] == DocumentStatus.FAILED
    assert any(
        update.get("ExpressionAttributeValues", {}).get(":status") == DocumentStatus.FAILED
        for update in table.updates
    )


def test_processor_marks_failed_on_dynamodb_update_error() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    table.fail_update_with(ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "UpdateItem"))
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    with pytest.raises(ClientError):
        processor.process("doc-1")


def test_sqs_worker_processes_and_deletes_created_event() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(item)), "documents")
    sqs = FakeSqsClient(
        [
            {
                "Body": '{"event_type":"DocumentCreated","document_id":"doc-1"}',
                "ReceiptHandle": "receipt-1",
            }
        ]
    )
    worker = SqsWorker(sqs, "document-events", processor)

    processed_count = worker.run_once()

    assert processed_count == 1
    assert sqs.deleted == ["receipt-1"]


def test_sqs_worker_deletes_invalid_json_message() -> None:
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")
    sqs = FakeSqsClient(
        [
            {
                "Body": "not-json",
                "ReceiptHandle": "receipt-invalid",
            }
        ]
    )
    worker = SqsWorker(sqs, "document-events", processor)

    processed_count = worker.run_once()

    assert processed_count == 1
    assert sqs.deleted == ["receipt-invalid"]


def test_sqs_worker_handles_nonexistent_queue() -> None:
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")
    sqs = FakeSqsClient()
    sqs.fail_queue_with(make_queue_does_not_exist_error())
    worker = SqsWorker(sqs, "document-events", processor)

    processed_count = worker.run_once()

    assert processed_count == 0


def test_sqs_worker_propagates_unknown_client_error() -> None:
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")
    sqs = FakeSqsClient()
    sqs.fail_receive_with(
        ClientError({"Error": {"Code": "AccessDeniedException"}}, "ReceiveMessage")
    )
    worker = SqsWorker(sqs, "document-events", processor)

    with pytest.raises(ClientError):
        worker.run_once()


def test_sqs_worker_skips_unknown_event_type() -> None:
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")
    sqs = FakeSqsClient(
        [
            {
                "Body": '{"event_type":"DocumentUpdated","document_id":"doc-1"}',
                "ReceiptHandle": "receipt-unknown",
            }
        ]
    )
    worker = SqsWorker(sqs, "document-events", processor)

    processed_count = worker.run_once()

    assert processed_count == 1
    assert sqs.deleted == ["receipt-unknown"]


def test_lambda_handler_processes_document_created():
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    event = {
        "Records": [{
            "messageId": "msg-1",
            "body": json.dumps({"event_type": "DocumentCreated", "document_id": "doc-1"})
        }]
    }

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 1
    assert result["results"][0]["document_id"] == "doc-1"
    assert result["results"][0]["result"] == "processed"
    assert item["status"] == "processed"
    assert "batchItemFailures" not in result


def test_lambda_handler_handles_invalid_json():
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")

    event = {
        "Records": [{"messageId": "msg-bad", "body": "not-valid-json"}]
    }

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert result["results"][0]["error"] == "invalid_record"
    assert "batchItemFailures" in result
    assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-bad"


def test_lambda_handler_skips_unsupported_events():
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(item)), "documents")

    event = {
        "Records": [{
            "body": json.dumps({"event_type": "DocumentUpdated", "document_id": "doc-1"})
        }]
    }

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert result["results"] == []


def test_lambda_handler_empty_records():
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")

    event = {"Records": []}

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert result["results"] == []


def test_lambda_handler_missing_body_key():
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")

    event = {"Records": [{"messageId": "msg-nobody", "other_field": "value"}]}

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert result["results"][0]["error"] == "invalid_record"
    assert "batchItemFailures" in result
    assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-nobody"


def test_lambda_handler_batch_with_partial_failure():
    items = {
        "doc-1": {
            "id": "doc-1",
            "bucket": "poc-local-documents",
            "object_key": "documents/doc-1/example.txt",
            "status": "created",
        },
    }

    class MultiItemTable:
        def __init__(self, initial: dict[str, dict]) -> None:
            self.items = dict(initial)
            self.updates: list = []

        def get_item(self, Key):
            item = self.items.get(Key["id"])
            return {"Item": item} if item else {}

        def update_item(self, **kwargs):
            self.updates.append(kwargs)
            kid = kwargs["Key"]["id"]
            values = kwargs.get("ExpressionAttributeValues", {})
            if kid in self.items:
                if ":status" in values:
                    self.items[kid]["status"] = values[":status"]
                if ":size" in values:
                    self.items[kid]["size"] = values[":size"]
                if ":processed_at" in values:
                    self.items[kid]["processed_at"] = values[":processed_at"]

    table = MultiItemTable(items)
    s3 = FakeS3Client()
    processor = DocumentProcessor(s3, FakeDynamoResource(table), "documents")

    event = {
        "Records": [
            {"messageId": "msg-1", "body": json.dumps({"event_type": "DocumentCreated", "document_id": "doc-1"})},
            {"messageId": "msg-2", "body": "not-valid-json"},
            {"messageId": "msg-3", "body": json.dumps({"event_type": "DocumentCreated", "document_id": "doc-missing"})},
        ]
    }

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 1
    assert len(result["results"]) == 3
    assert result["results"][0]["result"] == "processed"
    assert result["results"][1]["error"] == "invalid_record"
    assert result["results"][2]["result"] == "missing"
    assert "batchItemFailures" in result
    assert len(result["batchItemFailures"]) == 1
    assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-2"


def test_lambda_handler_returns_batch_item_failures_for_errors():
    """Verify that unhandled processor exceptions are reported as batch failures."""
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    s3 = FakeS3Client()
    s3.fail_with(ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject"))
    processor = DocumentProcessor(s3, FakeDynamoResource(table), "documents")

    event = {
        "Records": [
            {"messageId": "msg-err", "body": json.dumps({"event_type": "DocumentCreated", "document_id": "doc-1"})},
        ]
    }

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert "batchItemFailures" in result
    assert len(result["batchItemFailures"]) == 1
    assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-err"
    assert result["results"][0]["error"]


def test_lambda_handler_returns_batch_item_failures_for_locked():
    """Verify that locked documents are reported as batch failures for retry."""
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)

    original_update_item = table.update_item

    def conditional_update(**kwargs):
        cond = kwargs.get("ConditionExpression", "")
        if "attribute_not_exists(processing_owner)" in cond:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "locked"}},
                "UpdateItem",
            )
        original_update_item(**kwargs)

    table.update_item = conditional_update
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    event = {
        "Records": [
            {"messageId": "msg-locked", "body": json.dumps({"event_type": "DocumentCreated", "document_id": "doc-1"})},
        ]
    }

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert "batchItemFailures" in result
    assert len(result["batchItemFailures"]) == 1
    assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-locked"
    assert result["results"][0]["result"] == "locked"


def test_lambda_handler_no_batch_item_failures_on_full_success():
    """Verify that batchItemFailures is absent when all records succeed."""
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    event = {
        "Records": [
            {"messageId": "msg-ok", "body": json.dumps({"event_type": "DocumentCreated", "document_id": "doc-1"})},
        ]
    }

    with patch("handler._get_lambda_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 1
    assert "batchItemFailures" not in result


def test_processor_returns_locked_when_another_worker_holds_lock() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)

    original_update_item = table.update_item

    call_count = 0

    def conditional_update(**kwargs):
        nonlocal call_count
        call_count += 1
        cond = kwargs.get("ConditionExpression", "")
        if call_count == 1 and "attribute_not_exists(processing_owner)" in cond:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional check failed"}},
                "UpdateItem",
            )
        original_update_item(**kwargs)

    table.update_item = conditional_update
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "locked"


def test_processor_logs_when_failed_status_update_also_fails() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    s3 = FakeS3Client()
    s3.fail_with(ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject"))
    processor = DocumentProcessor(s3, FakeDynamoResource(table), "documents")

    original_update_item = table.update_item

    fail_status_update_count = 0

    def selective_fail(**kwargs):
        nonlocal fail_status_update_count
        values = kwargs.get("ExpressionAttributeValues", {})
        expr = kwargs.get("UpdateExpression", "")
        if ":status" in values and values[":status"] == DocumentStatus.FAILED:
            fail_status_update_count += 1
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException"}},
                "UpdateItem",
            )
        if "processing_owner" in expr and "REMOVE" in expr:
            return
        original_update_item(**kwargs)

    table.update_item = selective_fail

    with pytest.raises(ClientError):
        processor.process("doc-1")

    assert fail_status_update_count >= 1


def test_processor_tolerates_release_lock_error() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)

    original_update_item = table.update_item

    def fail_on_remove(**kwargs):
        expr = kwargs.get("UpdateExpression", "")
        if "REMOVE" in expr and "processing_owner" in expr:
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException"}},
                "UpdateItem",
            )
        original_update_item(**kwargs)

    table.update_item = fail_on_remove
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "processed"


def test_processor_force_releases_expired_lock() -> None:
    expired_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
        "processing_owner": "stale-worker",
        "processing_started_at": expired_at,
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "processed"
    assert item["status"] == DocumentStatus.PROCESSED
    assert "processing_owner" not in item
    assert "processing_started_at" not in item


def test_force_release_expired_lock_does_not_use_owner_condition() -> None:
    """Verify that force_release_expired_lock removes the lock without
    checking the owner, allowing recovery when the original worker is dead."""
    expired_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "processing",
        "processing_owner": "dead-worker-abc",
        "processing_started_at": expired_at,
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    processor._force_release_expired_lock("doc-1")

    assert "processing_owner" not in item
    assert "processing_started_at" not in item
    assert len(table.updates) == 1
    assert "REMOVE" in table.updates[0].get("UpdateExpression", "")


def test_processor_returns_locked_when_lock_not_expired() -> None:
    """When a lock exists and is NOT expired, returns False (locked)."""
    recent_at = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
        "processing_owner": "active-worker",
        "processing_started_at": recent_at,
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "locked"
    assert item.get("processing_owner") == "active-worker"


def test_processor_returns_locked_when_owner_without_started_at() -> None:
    """When a lock has owner but no processing_started_at, returns False."""
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
        "processing_owner": "some-worker",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "locked"


def test_force_release_expired_lock_tolerates_client_error() -> None:
    """Verify that _force_release_expired_lock logs and tolerates ClientError."""
    from unittest.mock import MagicMock

    failing_table = MagicMock()
    failing_table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}},
        "UpdateItem",
    )

    dynamodb_resource = MagicMock()
    dynamodb_resource.Table.return_value = failing_table

    processor = DocumentProcessor(FakeS3Client(), dynamodb_resource, "documents")

    processor._force_release_expired_lock("doc-1")

    failing_table.update_item.assert_called_once()


def test_processor_uses_consistent_owner_identifier() -> None:
    """Verify that lock acquire and release use the same owner identifier."""
    import os
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    owner = processor._resolve_owner()
    assert owner
    assert "uuid" not in owner.lower()
    assert owner == (os.environ.get("HOSTNAME")
                     or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
                     or "lambda-worker")


def test_sqs_worker_does_not_delete_on_locked_result() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)

    original_update_item = table.update_item

    def conditional_update(**kwargs):
        cond = kwargs.get("ConditionExpression", "")
        if "attribute_not_exists(processing_owner)" in cond:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "locked"}},
                "UpdateItem",
            )
        original_update_item(**kwargs)

    table.update_item = conditional_update
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")
    sqs = FakeSqsClient(
        [
            {
                "Body": '{"event_type":"DocumentCreated","document_id":"doc-1"}',
                "ReceiptHandle": "receipt-locked",
            }
        ]
    )
    worker = SqsWorker(sqs, "document-events", processor)

    processed_count = worker.run_once()

    assert processed_count == 1
    assert sqs.deleted == []


def test_sqs_worker_does_not_delete_on_processor_exception() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "created",
    }
    table = FakeTable(item)
    s3 = FakeS3Client()
    s3.fail_with(ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject"))
    processor = DocumentProcessor(s3, FakeDynamoResource(table), "documents")
    sqs = FakeSqsClient(
        [
            {
                "Body": '{"event_type":"DocumentCreated","document_id":"doc-1"}',
                "ReceiptHandle": "receipt-error",
            }
        ]
    )
    worker = SqsWorker(sqs, "document-events", processor)

    processed_count = worker.run_once()

    assert processed_count == 1
    assert sqs.deleted == []
