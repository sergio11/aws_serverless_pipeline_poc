from io import BytesIO
import json
import os
from unittest.mock import patch

from handler import DocumentProcessor, DocumentStatus, SqsWorker


class FakeS3Client:
    def __init__(self, content: bytes = b"Hello AWS") -> None:
        self.content = content

    def get_object(self, Bucket: str, Key: str) -> dict[str, BytesIO]:
        return {"Body": BytesIO(self.content)}


class FakeTable:
    def __init__(self, item: dict[str, object] | None) -> None:
        self.item = item
        self.updates: list[dict[str, object]] = []

    def get_item(self, Key: dict[str, str]) -> dict[str, dict[str, object]]:
        return {"Item": self.item} if self.item else {}

    def update_item(self, **kwargs) -> None:
        self.updates.append(kwargs)
        values = kwargs.get("ExpressionAttributeValues", {})
        if self.item is not None:
            if ":status" in values:
                self.item["status"] = values[":status"]
            if ":size" in values:
                self.item["size"] = values[":size"]
            if ":processed_at" in values:
                self.item["processed_at"] = values[":processed_at"]
            if "processing_owner" in kwargs.get("UpdateExpression", ""):
                if "REMOVE" in kwargs.get("UpdateExpression", ""):
                    self.item.pop("processing_owner", None)
                elif ":owner" in values:
                    self.item["processing_owner"] = values[":owner"]


class FakeDynamoResource:
    def __init__(self, table: FakeTable) -> None:
        self.table = table

    def Table(self, table_name: str) -> FakeTable:
        return self.table


class FakeSqsClient:
    def __init__(self, messages: list[dict[str, str]]) -> None:
        self.messages = messages
        self.deleted: list[str] = []

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"http://floci:4566/000000000000/{QueueName}"}

    def receive_message(self, **kwargs) -> dict[str, list[dict[str, str]]]:
        return {"Messages": self.messages}

    def delete_message(self, QueueUrl: str, ReceiptHandle: str) -> None:
        self.deleted.append(ReceiptHandle)


def test_processor_marks_document_processed() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "CREATED",
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
        "status": "PROCESSED",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    result = processor.process("doc-1")

    assert result == "skipped"
    assert table.updates == []


def test_sqs_worker_processes_and_deletes_created_event() -> None:
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "CREATED",
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


def test_lambda_handler_processes_document_created():
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "CREATED",
    }
    table = FakeTable(item)
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(table), "documents")

    event = {
        "Records": [{
            "body": json.dumps({"event_type": "DocumentCreated", "document_id": "doc-1"})
        }]
    }

    with patch("handler.create_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 1
    assert result["results"][0]["document_id"] == "doc-1"
    assert result["results"][0]["result"] == "processed"
    assert item["status"] == "PROCESSED"


def test_lambda_handler_handles_invalid_json():
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(None)), "documents")

    event = {
        "Records": [{"body": "not-valid-json"}]
    }

    with patch("handler.create_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert result["results"][0]["error"] == "invalid_record"


def test_lambda_handler_skips_unsupported_events():
    item = {
        "id": "doc-1",
        "bucket": "poc-local-documents",
        "object_key": "documents/doc-1/example.txt",
        "status": "CREATED",
    }
    processor = DocumentProcessor(FakeS3Client(), FakeDynamoResource(FakeTable(item)), "documents")

    event = {
        "Records": [{
            "body": json.dumps({"event_type": "DocumentUpdated", "document_id": "doc-1"})
        }]
    }

    with patch("handler.create_processor", return_value=processor):
        from handler import lambda_handler
        result = lambda_handler(event, None)

    assert result["processed"] == 0
    assert result["results"] == []
