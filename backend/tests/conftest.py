from io import BytesIO


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
