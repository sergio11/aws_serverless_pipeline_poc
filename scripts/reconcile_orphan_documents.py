#!/usr/bin/env python3
"""Reconcile orphaned documents stuck in CREATED or PROCESSING state."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta

import boto3
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile orphaned documents.")
    parser.add_argument("--endpoint-url", default="http://localhost:4566")
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--table", default="documents")
    parser.add_argument("--queue", default="document-events")
    parser.add_argument("--max-age-minutes", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def scan_stale_documents(table, max_age_minutes: int) -> list[dict]:
    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
    stale = []
    last_key = None

    while True:
        kwargs: dict = {"FilterExpression": "#s = :created OR #s = :processing"}
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
        kwargs["ExpressionAttributeValues"] = {
            ":created": "created",
            ":processing": "processing",
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        response = table.scan(**kwargs)
        for item in response.get("Items", []):
            created_at = datetime.fromisoformat(item["created_at"]).astimezone(UTC)
            if created_at < cutoff:
                stale.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return stale


def send_requeue_message(sqs, queue_url: str, document_id: str, dry_run: bool) -> None:
    message = {"event_type": "DocumentCreated", "document_id": document_id}
    if dry_run:
        print(f"  [dry-run] Would send: {json.dumps(message)}")
        return
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message))
    print(f"  Requeued document {document_id}")


def reset_processing_lock(table, document_id: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] Would reset lock for {document_id}")
        return
    table.update_item(
        Key={"id": document_id},
        UpdateExpression="SET #s = :created REMOVE processing_owner, processing_started_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":created": "created"},
    )
    print(f"  Reset lock for {document_id}")


def main() -> None:
    args = parse_args()

    config = {
        "endpoint_url": args.endpoint_url,
        "region_name": args.region,
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    }

    dynamodb = boto3.resource("dynamodb", **config)
    sqs = boto3.client("sqs", **config)
    table = dynamodb.Table(args.table)

    try:
        queue_url = sqs.get_queue_url(QueueName=args.queue)["QueueUrl"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {
            "AWS.SimpleQueueService.NonExistentQueue",
            "QueueDoesNotExist",
        }:
            print(f"Queue {args.queue} does not exist. Create it first.")
            sys.exit(1)
        raise

    print(f"Scanning for documents stale longer than {args.max_age_minutes} minutes...")
    stale = scan_stale_documents(table, args.max_age_minutes)
    print(f"Found {len(stale)} orphaned document(s).")

    if not stale:
        return

    for item in stale:
        doc_id = item["id"]
        status = item["status"]
        print(f"\nDocument {doc_id} (status={status}):")

        if status == "processing":
            reset_processing_lock(table, doc_id, args.dry_run)

        send_requeue_message(sqs, queue_url, doc_id, args.dry_run)

    print(f"\nReconciliation complete. Processed {len(stale)} document(s).")


if __name__ == "__main__":
    main()
