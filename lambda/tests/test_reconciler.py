import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from reconciler import (
    log_event,
    reset_processing_lock,
    run_reconciliation,
    scan_stale_documents,
    send_requeue_message,
)


class FakeReconcilerTable:
    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []
        self.scan_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self._scan_pages: list[list[dict]] | None = None

    def set_scan_pages(self, pages: list[list[dict]]) -> None:
        self._scan_pages = pages

    def scan(self, **kwargs) -> dict:
        self.scan_calls.append(kwargs)
        if self._scan_pages is not None:
            page_idx = len(self.scan_calls) - 1
            if page_idx < len(self._scan_pages):
                page = self._scan_pages[page_idx]
            else:
                page = []
            result: dict = {"Items": page}
            if page_idx < len(self._scan_pages) - 1:
                result["LastEvaluatedKey"] = {"id": page[-1]["id"]} if page else {}
            return result
        filter_expr = kwargs.get("FilterExpression", "")
        values = kwargs.get("ExpressionAttributeValues", {})
        filtered = []
        for item in self.items:
            status = item.get("status", "")
            if "#s = :created OR #s = :processing" in filter_expr:
                if status not in (values.get(":created"), values.get(":processing")):
                    continue
            filtered.append(item)
        return {"Items": filtered}

    def update_item(self, **kwargs) -> None:
        self.update_calls.append(kwargs)


class FakeReconcilerSqs:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self._queue_url_error: Exception | None = None

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        if self._queue_url_error:
            raise self._queue_url_error
        return {"QueueUrl": f"http://floci:4566/000000000000/{QueueName}"}

    def send_message(self, QueueUrl: str, MessageBody: str) -> None:
        self.sent_messages.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})

    def fail_queue_with(self, error: Exception) -> None:
        self._queue_url_error = error


def _make_mock_boto3(table: FakeReconcilerTable, sqs: FakeReconcilerSqs) -> tuple[MagicMock, MagicMock]:
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = table
    mock_sqs = MagicMock(spec=FakeReconcilerSqs)
    mock_sqs.get_queue_url = sqs.get_queue_url
    mock_sqs.send_message = sqs.send_message
    return mock_dynamodb, mock_sqs


def test_log_event() -> None:
    import logging
    log_event(logging.INFO, "test_event", key="value")


def test_scan_stale_documents_returns_stale_items() -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    fresh_at = datetime.now(UTC).isoformat()
    items = [
        {"id": "doc-1", "status": "created", "created_at": stale_at},
        {"id": "doc-2", "status": "created", "created_at": fresh_at},
        {"id": "doc-3", "status": "processing", "created_at": stale_at},
    ]
    table = FakeReconcilerTable(items)

    stale = scan_stale_documents(table, max_age_minutes=10)

    assert len(stale) == 2
    assert stale[0]["id"] == "doc-1"
    assert stale[1]["id"] == "doc-3"
    assert len(table.scan_calls) == 1


def test_scan_stale_documents_handles_pagination() -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    table = FakeReconcilerTable()
    table.set_scan_pages([
        [
            {"id": "doc-1", "status": "created", "created_at": stale_at},
            {"id": "doc-2", "status": "processing", "created_at": stale_at},
        ],
        [
            {"id": "doc-3", "status": "created", "created_at": stale_at},
        ],
    ])

    stale = scan_stale_documents(table, max_age_minutes=10)

    assert len(stale) == 3
    assert len(table.scan_calls) == 2


def test_scan_stale_documents_filters_recent_items() -> None:
    fresh_at = datetime.now(UTC).isoformat()
    items = [
        {"id": "doc-1", "status": "created", "created_at": fresh_at},
        {"id": "doc-2", "status": "processing", "created_at": fresh_at},
    ]
    table = FakeReconcilerTable(items)

    stale = scan_stale_documents(table, max_age_minutes=10)

    assert len(stale) == 0


def test_scan_stale_documents_ignores_processed_status() -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    items = [
        {"id": "doc-1", "status": "processed", "created_at": stale_at},
    ]
    table = FakeReconcilerTable(items)

    stale = scan_stale_documents(table, max_age_minutes=10)

    assert len(stale) == 0


def test_scan_stale_documents_empty_table() -> None:
    table = FakeReconcilerTable([])

    stale = scan_stale_documents(table, max_age_minutes=10)

    assert len(stale) == 0


def test_send_requeue_message() -> None:
    sqs = FakeReconcilerSqs()

    send_requeue_message(sqs, "http://queue-url", "doc-1")

    assert len(sqs.sent_messages) == 1
    body = json.loads(sqs.sent_messages[0]["MessageBody"])
    assert body["event_type"] == "DocumentCreated"
    assert body["document_id"] == "doc-1"


def test_reset_processing_lock_success() -> None:
    table = FakeReconcilerTable()

    result = reset_processing_lock(table, "doc-1")

    assert result is True
    assert len(table.update_calls) == 1
    update = table.update_calls[0]
    assert "SET #s = :created" in update["UpdateExpression"]
    assert "REMOVE processing_owner" in update["UpdateExpression"]
    assert "processing_started_at" in update["UpdateExpression"]


def test_reset_processing_lock_failure() -> None:
    table = FakeReconcilerTable()
    table.update_item = MagicMock(side_effect=ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}},
        "UpdateItem",
    ))

    result = reset_processing_lock(table, "doc-1")

    assert result is False


@patch("reconciler.boto3")
def test_run_reconciliation_no_stale_documents(mock_boto3: MagicMock) -> None:
    fresh_at = datetime.now(UTC).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "created", "created_at": fresh_at},
    ])
    sqs = FakeReconcilerSqs()
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 0}
    assert len(sqs.sent_messages) == 0


@patch("reconciler.boto3")
def test_run_reconciliation_requeues_stale_created_documents(mock_boto3: MagicMock) -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "created", "created_at": stale_at},
    ])
    sqs = FakeReconcilerSqs()
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 1, "total": 1}
    assert len(sqs.sent_messages) == 1
    body = json.loads(sqs.sent_messages[0]["MessageBody"])
    assert body["document_id"] == "doc-1"


@patch("reconciler.boto3")
def test_run_reconciliation_resets_lock_on_processing_documents(mock_boto3: MagicMock) -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "processing", "created_at": stale_at},
    ])
    sqs = FakeReconcilerSqs()
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 1, "total": 1}
    assert len(table.update_calls) == 1
    assert len(sqs.sent_messages) == 1


@patch("reconciler.boto3")
def test_run_reconciliation_skips_if_lock_reset_fails(mock_boto3: MagicMock) -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "processing", "created_at": stale_at},
    ])
    table.update_item = MagicMock(side_effect=ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}},
        "UpdateItem",
    ))
    sqs = FakeReconcilerSqs()
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 0, "total": 1}
    assert len(sqs.sent_messages) == 0


@patch("reconciler.boto3")
def test_run_reconciliation_handles_queue_not_found(mock_boto3: MagicMock) -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "created", "created_at": stale_at},
    ])
    sqs = FakeReconcilerSqs()
    sqs.fail_queue_with(ClientError(
        {"Error": {"Code": "AWS.SimpleQueueService.NonExistentQueue"}},
        "GetQueueUrl",
    ))
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 0, "error": "queue_not_found"}


@patch("reconciler.boto3")
def test_run_reconciliation_raises_other_client_errors(mock_boto3: MagicMock) -> None:
    table = FakeReconcilerTable([])
    sqs = FakeReconcilerSqs()
    sqs.fail_queue_with(ClientError(
        {"Error": {"Code": "AccessDeniedException"}},
        "GetQueueUrl",
    ))
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    with pytest.raises(ClientError):
        run_reconciliation(
            {"endpoint_url": "http://localhost:4566"},
            "test-table",
            "test-queue",
            max_age_minutes=10,
        )


@patch("reconciler.boto3")
def test_run_reconciliation_mixed_created_and_processing(mock_boto3: MagicMock) -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "created", "created_at": stale_at},
        {"id": "doc-2", "status": "processing", "created_at": stale_at},
        {"id": "doc-3", "status": "created", "created_at": stale_at},
    ])
    sqs = FakeReconcilerSqs()
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 3, "total": 3}
    assert len(sqs.sent_messages) == 3


@patch.dict("os.environ", {
    "AWS_ENDPOINT_URL": "http://localhost:4566",
    "DYNAMODB_TABLE": "test-table",
    "SQS_QUEUE_NAME": "test-queue",
    "RECONCILER_MAX_AGE_MINUTES": "10",
})
@patch("reconciler.run_reconciliation")
def test_handler_calls_run_reconciliation(mock_run: MagicMock) -> None:
    mock_run.return_value = {"reconciled": 2}
    from reconciler import handler

    result = handler({}, None)

    assert result == {"reconciled": 2}
    mock_run.assert_called_once()


@patch.dict("os.environ", {
    "AWS_ENDPOINT_URL": "http://localhost:4566",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "mykey",
    "AWS_SECRET_ACCESS_KEY": "mysecret",
    "DYNAMODB_TABLE": "my-table",
    "SQS_QUEUE_NAME": "my-queue",
    "RECONCILER_MAX_AGE_MINUTES": "5",
})
@patch("reconciler.run_reconciliation")
def test_handler_passes_config_correctly(mock_run: MagicMock) -> None:
    mock_run.return_value = {"reconciled": 0}
    from reconciler import handler

    handler({}, None)

    call_args = mock_run.call_args
    config = call_args[0][0]
    assert config["endpoint_url"] == "http://localhost:4566"
    assert config["region_name"] == "us-east-1"
    assert config["aws_access_key_id"] == "mykey"
    assert config["aws_secret_access_key"] == "mysecret"
    assert call_args[0][1] == "my-table"
    assert call_args[0][2] == "my-queue"
    assert call_args[0][3] == 5


@patch.dict("os.environ", {
    "AWS_ENDPOINT_URL": "http://localhost:4566",
    "DYNAMODB_TABLE": "test-table",
    "SQS_QUEUE_NAME": "test-queue",
})
@patch("reconciler.run_reconciliation")
def test_handler_uses_default_values(mock_run: MagicMock) -> None:
    mock_run.return_value = {"reconciled": 0}
    from reconciler import handler

    handler({}, None)

    call_args = mock_run.call_args
    config = call_args[0][0]
    assert config["region_name"] == "eu-west-1"
    assert config["aws_access_key_id"] == "test"
    assert config["aws_secret_access_key"] == "test"
    assert call_args[0][3] == 10


@patch("reconciler.boto3")
def test_run_reconciliation_handles_queue_does_not_exist_error_code(mock_boto3: MagicMock) -> None:
    stale_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "created", "created_at": stale_at},
    ])
    sqs = FakeReconcilerSqs()
    sqs.fail_queue_with(ClientError(
        {"Error": {"Code": "QueueDoesNotExist"}},
        "GetQueueUrl",
    ))
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 0, "error": "queue_not_found"}


@patch("reconciler.boto3")
def test_run_reconciliation_skips_recent_processing_document(mock_boto3: MagicMock) -> None:
    recent_at = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    table = FakeReconcilerTable([
        {"id": "doc-1", "status": "processing", "created_at": recent_at},
    ])
    sqs = FakeReconcilerSqs()
    mock_dynamodb, mock_sqs = _make_mock_boto3(table, sqs)
    mock_boto3.resource.return_value = mock_dynamodb
    mock_boto3.client.return_value = mock_sqs

    result = run_reconciliation(
        {"endpoint_url": "http://localhost:4566"},
        "test-table",
        "test-queue",
        max_age_minutes=10,
    )

    assert result == {"reconciled": 0}
    assert len(table.update_calls) == 0
    assert len(sqs.sent_messages) == 0
