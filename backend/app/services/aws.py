import json
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.domain import Document
from app.settings import Settings


class AwsDocumentStore:
    def __init__(self, settings: Settings) -> None:
        client_config = {
            "endpoint_url": settings.aws_endpoint_url,
            "region_name": settings.aws_region,
            "aws_access_key_id": settings.aws_access_key_id,
            "aws_secret_access_key": settings.aws_secret_access_key,
        }
        self._bucket_name = settings.s3_bucket
        self._table_name = settings.dynamodb_table
        self._queue_name = settings.sqs_queue_name
        self._s3 = boto3.client("s3", **client_config)
        self._dynamodb = boto3.resource("dynamodb", **client_config)
        self._sqs = boto3.client("sqs", **client_config)
        self._table = self._dynamodb.Table(self._table_name)
        self._queue_url: str | None = None

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def build_object_key(self, document_id: str, filename: str) -> str:
        return f"documents/{document_id}/{filename}"

    def save(self, document: Document, content: str) -> None:
        self._s3.put_object(
            Bucket=document.bucket,
            Key=document.object_key,
            Body=content.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        self._table.put_item(Item=self._serialize_document(document))

    def get(self, document_id: str) -> Document | None:
        response = self._table.get_item(Key={"id": document_id})
        item = response.get("Item")
        if item is None:
            return None
        return self._deserialize_document(item)

    def get_content(self, document_id: str) -> str | None:
        document = self.get(document_id)
        if document is None:
            return None

        try:
            response = self._s3.get_object(Bucket=document.bucket, Key=document.object_key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise

        body = response["Body"].read()
        return body.decode("utf-8")

    def publish_created(self, document_id: str) -> None:
        message = {
            "event_type": "DocumentCreated",
            "document_id": document_id,
        }
        self._sqs.send_message(
            QueueUrl=self._get_queue_url(),
            MessageBody=json.dumps(message),
        )

    def delete(self, document_id: str) -> None:
        """Elimina un documento de S3 y DynamoDB."""
        document = self.get(document_id)
        if document is None:
            return
        try:
            self._s3.delete_object(Bucket=document.bucket, Key=document.object_key)
        except ClientError:
            pass
        try:
            self._table.delete_item(Key={"id": document_id})
        except ClientError:
            pass

    def _get_queue_url(self) -> str:
        if self._queue_url is None:
            response = self._sqs.get_queue_url(QueueName=self._queue_name)
            self._queue_url = response["QueueUrl"]
        return self._queue_url

    def _serialize_document(self, document: Document) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": document.id,
            "name": document.name,
            "bucket": document.bucket,
            "object_key": document.object_key,
            "size": document.size,
            "status": document.status,
            "created_at": document.created_at.isoformat(),
        }
        if document.processed_at is not None:
            item["processed_at"] = document.processed_at.isoformat()
        return item

    def _deserialize_document(self, item: dict[str, Any]) -> Document:
        processed_at = item.get("processed_at")
        return Document(
            id=item["id"],
            name=item["name"],
            bucket=item["bucket"],
            object_key=item["object_key"],
            size=int(item["size"]),
            status=item["status"],
            created_at=datetime.fromisoformat(item["created_at"]).astimezone(UTC),
            processed_at=datetime.fromisoformat(processed_at).astimezone(UTC) if processed_at else None,
        )
