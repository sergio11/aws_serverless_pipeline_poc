from io import BytesIO

from botocore.exceptions import ClientError


class FakeS3Client:
    def __init__(self, content: bytes = b"Hello AWS") -> None:
        self.content = content
        self._raise_error: Exception | None = None

    def get_object(self, Bucket: str, Key: str) -> dict[str, BytesIO]:
        if self._raise_error:
            raise self._raise_error
        return {"Body": BytesIO(self.content)}

    def fail_with(self, error: Exception) -> None:
        self._raise_error = error


class FakeTable:
    def __init__(self, item: dict[str, object] | None) -> None:
        self.item = item
        self.updates: list[dict[str, object]] = []
        self._raise_on_update: Exception | None = None

    def get_item(self, Key: dict[str, str]) -> dict[str, dict[str, object]]:
        return {"Item": self.item} if self.item else {}

    def update_item(self, **kwargs) -> None:
        if self._raise_on_update:
            raise self._raise_on_update
        self.updates.append(kwargs)
        values = kwargs.get("ExpressionAttributeValues", {})
        if self.item is not None:
            if ":status" in values:
                self.item["status"] = values[":status"]
            if ":size" in values:
                self.item["size"] = values[":size"]
            if ":processed_at" in values:
                self.item["processed_at"] = values[":processed_at"]
            if ":owner" in values:
                self.item["processing_owner"] = values[":owner"]
            if ":started_at" in values:
                self.item["processing_started_at"] = values[":started_at"]
            remove_expr = kwargs.get("UpdateExpression", "")
            if "REMOVE" in remove_expr:
                if "processing_owner" in remove_expr:
                    self.item.pop("processing_owner", None)
                if "processing_started_at" in remove_expr:
                    self.item.pop("processing_started_at", None)

    def fail_update_with(self, error: Exception) -> None:
        self._raise_on_update = error


class FakeDynamoResource:
    def __init__(self, table: FakeTable) -> None:
        self.table = table

    def Table(self, table_name: str) -> FakeTable:
        return self.table


class FakeSqsClient:
    def __init__(self, messages: list[dict[str, str]] | None = None) -> None:
        self.messages = messages or []
        self.deleted: list[str] = []
        self._queue_url_error: Exception | None = None
        self._receive_error: Exception | None = None

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        if self._queue_url_error:
            raise self._queue_url_error
        return {"QueueUrl": f"http://floci:4566/000000000000/{QueueName}"}

    def receive_message(self, **kwargs) -> dict[str, list[dict[str, str]]]:
        if self._receive_error:
            raise self._receive_error
        return {"Messages": self.messages}

    def delete_message(self, QueueUrl: str, ReceiptHandle: str) -> None:
        self.deleted.append(ReceiptHandle)

    def fail_queue_with(self, error: Exception) -> None:
        self._queue_url_error = error

    def fail_receive_with(self, error: Exception) -> None:
        self._receive_error = error


def make_queue_does_not_exist_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "AWS.SimpleQueueService.NonExistentQueue", "Message": "Queue does not exist"}},
        "GetQueueUrl",
    )
