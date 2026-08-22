from datetime import UTC, datetime
from io import BytesIO

from botocore.exceptions import ClientError

from app.domain import Document, DocumentStatus
from app.services.aws import AwsDocumentStore
from app.settings import Settings


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self._get_error: ClientError | None = None
        self._list_buckets_error: Exception | None = None

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, BytesIO]:
        if self._get_error:
            raise self._get_error
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def list_buckets(self) -> dict[str, list]:
        if self._list_buckets_error:
            raise self._list_buckets_error
        return {"Buckets": []}

    def fail_get_with(self, error: ClientError) -> None:
        self._get_error = error

    def fail_list_buckets_with(self, error: Exception) -> None:
        self._list_buckets_error = error


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def put_item(self, Item: dict[str, object]) -> None:
        self.items[str(Item["id"])] = Item

    def get_item(self, Key: dict[str, str]) -> dict[str, dict[str, object]]:
        item = self.items.get(Key["id"])
        return {"Item": item} if item else {}

    def delete_item(self, Key: dict[str, str], **kwargs) -> None:
        self.items.pop(Key["id"], None)


class FakeDynamoClient:
    def __init__(self) -> None:
        self._list_tables_error: Exception | None = None

    def list_tables(self) -> dict[str, list]:
        if self._list_tables_error:
            raise self._list_tables_error
        return {"TableNames": []}

    def fail_list_tables_with(self, error: Exception) -> None:
        self._list_tables_error = error


class FakeDynamoResource:
    def __init__(self, table: FakeTable) -> None:
        self.table = table
        self.meta = self

    def Table(self, table_name: str) -> FakeTable:
        return self.table

    def __getattr__(self, name: str):
        if name == "client":
            return FakeDynamoClient()
        raise AttributeError(name)


class FakeSqsClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"http://floci:4566/000000000000/{QueueName}"}

    def send_message(self, QueueUrl: str, MessageBody: str) -> None:
        self.messages.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})


def _make_store(monkeypatch, s3=None, table=None, sqs=None):
    s3 = s3 or FakeS3Client()
    table = table or FakeTable()
    sqs = sqs or FakeSqsClient()

    def fake_client(service_name: str, **kwargs):
        return {"s3": s3, "sqs": sqs}[service_name]

    def fake_resource(service_name: str, **kwargs):
        assert service_name == "dynamodb"
        return FakeDynamoResource(table)

    monkeypatch.setattr("app.services.aws.boto3.client", fake_client)
    monkeypatch.setattr("app.services.aws.boto3.resource", fake_resource)

    return AwsDocumentStore(
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


def _make_document(**overrides) -> Document:
    defaults = dict(
        id="doc-1",
        name="example.txt",
        bucket="poc-local-documents",
        object_key="documents/doc-1/example.txt",
        size=9,
        status=DocumentStatus.CREATED,
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return Document(**defaults)


def test_aws_document_store_persists_content_metadata_and_event(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    document = _make_document()

    store.save(document, "Hello AWS")
    store.publish_created(document.id)

    assert store.get("doc-1") == document
    assert store.get_content("doc-1") == b"Hello AWS"


def test_round_trip_save_get_deserialize(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    created_at = datetime(2026, 3, 15, 10, 30, 0, tzinfo=UTC)
    processed_at = datetime(2026, 3, 15, 10, 31, 0, tzinfo=UTC)
    document = _make_document(
        status=DocumentStatus.PROCESSED,
        created_at=created_at,
        processed_at=processed_at,
    )

    store.save(document, "Round trip content")

    retrieved = store.get("doc-1")
    assert retrieved is not None
    assert retrieved.id == document.id
    assert retrieved.name == document.name
    assert retrieved.bucket == document.bucket
    assert retrieved.object_key == document.object_key
    assert retrieved.size == document.size
    assert retrieved.status == DocumentStatus.PROCESSED
    assert retrieved.created_at == created_at
    assert retrieved.processed_at == processed_at
    assert store.get_content("doc-1") == b"Round trip content"


def test_bucket_name_property(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    assert store.bucket_name == "poc-local-documents"


def test_build_object_key(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    key = store.build_object_key("abc-123", "test.txt")
    assert key == "documents/abc-123/test.txt"


def test_get_returns_none_for_nonexistent(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    assert store.get("nonexistent") is None


def test_get_content_returns_none_when_document_missing(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    assert store.get_content("nonexistent") is None


def test_get_content_returns_none_on_s3_nosuchkey(monkeypatch) -> None:
    s3 = FakeS3Client()
    s3.fail_get_with(ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject"))
    store = _make_store(monkeypatch, s3=s3)
    document = _make_document()
    store.save(document, "Hello AWS")

    assert store.get_content("doc-1") is None


def test_get_content_propagates_other_s3_errors(monkeypatch) -> None:
    s3 = FakeS3Client()
    s3.fail_get_with(ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject"))
    store = _make_store(monkeypatch, s3=s3)
    document = _make_document()
    store.save(document, "Hello AWS")

    try:
        store.get_content("doc-1")
        assert False, "Should have raised"
    except ClientError as e:
        assert e.response["Error"]["Code"] == "AccessDenied"


def test_delete_removes_document(monkeypatch) -> None:
    table = FakeTable()
    store = _make_store(monkeypatch, table=table)
    document = _make_document()
    store.save(document, "Hello AWS")

    store.delete("doc-1")

    assert store.get("doc-1") is None
    assert "doc-1" not in table.items


def test_delete_noop_for_nonexistent(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    store.delete("nonexistent")


def test_serialize_includes_processed_at(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    document = _make_document(
        status=DocumentStatus.PROCESSED,
        processed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save(document, "Hello AWS")

    stored = store.get("doc-1")
    assert stored is not None
    assert stored.processed_at is not None
    assert stored.status == DocumentStatus.PROCESSED


class FailingDeleteS3Client(FakeS3Client):
    def delete_object(self, Bucket: str, Key: str) -> None:
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")


def test_delete_tolerates_s3_error(monkeypatch) -> None:
    s3 = FailingDeleteS3Client()
    table = FakeTable()
    store = _make_store(monkeypatch, s3=s3, table=table)
    document = _make_document()
    store.save(document, "Hello AWS")

    store.delete("doc-1")

    assert "doc-1" not in table.items


class FailingDeleteDynamoTable(FakeTable):
    def delete_item(self, Key: dict[str, str], **kwargs) -> None:
        raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "DeleteItem")


def test_delete_tolerates_dynamodb_error(monkeypatch) -> None:
    table = FailingDeleteDynamoTable()
    store = _make_store(monkeypatch, table=table)
    document = _make_document()
    store.save(document, "Hello AWS")

    store.delete("doc-1")


def test_health_check_all_ok(monkeypatch) -> None:
    store = _make_store(monkeypatch)
    result = store.health_check()
    assert result == {"s3": "ok", "dynamodb": "ok", "sqs": "ok"}


def test_health_check_reports_s3_error(monkeypatch) -> None:
    s3 = FakeS3Client()
    s3.fail_list_buckets_with(RuntimeError("S3 unavailable"))
    store = _make_store(monkeypatch, s3=s3)
    result = store.health_check()
    assert result["s3"] == "error"
    assert result["dynamodb"] == "ok"
    assert result["sqs"] == "ok"


def test_health_check_reports_dynamodb_error(monkeypatch) -> None:
    table = FakeTable()
    dynamo = FakeDynamoResource(table)
    dynamo.meta = type("obj", (), {"client": type("c", (), {"list_tables": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("DynamoDB unavailable")))})()})()

    def fake_resource(service_name: str, **kwargs):
        return dynamo

    monkeypatch.setattr("app.services.aws.boto3.resource", fake_resource)
    monkeypatch.setattr("app.services.aws.boto3.client", lambda s, **kw: FakeSqsClient())

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
    result = store.health_check()
    assert result["dynamodb"] == "error"


def test_health_check_reports_sqs_error(monkeypatch) -> None:
    class FailingSqsClient:
        def get_queue_url(self, QueueName: str) -> dict[str, str]:
            raise RuntimeError("SQS unavailable")

    store = _make_store(monkeypatch, sqs=FailingSqsClient())
    result = store.health_check()
    assert result["sqs"] == "error"
    assert result["s3"] == "ok"
    assert result["dynamodb"] == "ok"
