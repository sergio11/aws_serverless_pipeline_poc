from io import BytesIO

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
        values = kwargs["ExpressionAttributeValues"]
        if self.item is not None:
            if ":status" in values:
                self.item["status"] = values[":status"]
            if ":size" in values:
                self.item["size"] = values[":size"]
            if ":processed_at" in values:
                self.item["processed_at"] = values[":processed_at"]


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
