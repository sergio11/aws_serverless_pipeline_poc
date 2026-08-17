from datetime import UTC, datetime
from io import BytesIO

from app.domain import Document, DocumentStatus
from app.services.aws import AwsDocumentStore
from app.settings import Settings


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, BytesIO]:
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def put_item(self, Item: dict[str, object]) -> None:
        self.items[str(Item["id"])] = Item

    def get_item(self, Key: dict[str, str]) -> dict[str, dict[str, object]]:
        item = self.items.get(Key["id"])
        return {"Item": item} if item else {}


class FakeDynamoResource:
    def __init__(self, table: FakeTable) -> None:
        self.table = table

    def Table(self, table_name: str) -> FakeTable:
        return self.table


class FakeSqsClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"http://floci:4566/000000000000/{QueueName}"}

    def send_message(self, QueueUrl: str, MessageBody: str) -> None:
        self.messages.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})


def test_aws_document_store_persists_content_metadata_and_event(monkeypatch) -> None:
    s3 = FakeS3Client()
    table = FakeTable()
    sqs = FakeSqsClient()

    def fake_client(service_name: str, **kwargs):
        return {"s3": s3, "sqs": sqs}[service_name]

    def fake_resource(service_name: str, **kwargs):
        assert service_name == "dynamodb"
        return FakeDynamoResource(table)

    monkeypatch.setattr("app.services.aws.boto3.client", fake_client)
    monkeypatch.setattr("app.services.aws.boto3.resource", fake_resource)

    store = AwsDocumentStore(
        Settings(
            aws_endpoint_url="http://floci:4566",
            aws_region="eu-west-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
            s3_bucket="poc-local-documents",
            dynamodb_table="documents",
            sqs_queue_name="document-events",
        )
    )
    document = Document(
        id="doc-1",
        name="example.txt",
        bucket="poc-local-documents",
        object_key="documents/doc-1/example.txt",
        size=9,
        status=DocumentStatus.CREATED,
        created_at=datetime.now(UTC),
    )

    store.save(document, "Hello AWS")
    store.publish_created(document.id)

    assert store.get("doc-1") == document
    assert store.get_content("doc-1") == "Hello AWS"
    assert sqs.messages == [
        {
            "QueueUrl": "http://floci:4566/000000000000/document-events",
            "MessageBody": '{"event_type": "DocumentCreated", "document_id": "doc-1"}',
        }
    ]
