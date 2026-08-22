from io import BytesIO


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self._get_error: Exception | None = None
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

    def fail_get_with(self, error: Exception) -> None:
        self._get_error = error

    def fail_list_buckets_with(self, error: Exception) -> None:
        self._list_buckets_error = error


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}
        self._raise_on_delete: Exception | None = None

    def put_item(self, Item: dict[str, object]) -> None:
        self.items[str(Item["id"])] = Item

    def get_item(self, Key: dict[str, str]) -> dict[str, dict[str, object]]:
        item = self.items.get(Key["id"])
        return {"Item": item} if item else {}

    def delete_item(self, Key: dict[str, str], **kwargs) -> None:
        if self._raise_on_delete:
            raise self._raise_on_delete
        self.items.pop(Key["id"], None)

    def fail_delete_with(self, error: Exception) -> None:
        self._raise_on_delete = error


class FakeDynamoResource:
    def __init__(self, table: FakeTable) -> None:
        self.table = table
        self.meta = self

    def Table(self, table_name: str) -> FakeTable:
        return self.table

    def __getattr__(self, name: str):
        if name == "client":
            return type("obj", (), {"list_tables": staticmethod(lambda: {"TableNames": []})})()
        raise AttributeError(name)


class FakeSqsClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"http://floci:4566/000000000000/{QueueName}"}

    def send_message(self, QueueUrl: str, MessageBody: str) -> None:
        self.messages.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})
