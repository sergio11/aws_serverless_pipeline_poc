import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    aws_endpoint_url: str
    aws_region: str
    s3_bucket: str
    dynamodb_table: str
    sqs_queue_name: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            aws_endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
            aws_region=os.getenv("AWS_DEFAULT_REGION", "eu-west-1"),
            s3_bucket=os.getenv("S3_BUCKET", "poc-documents"),
            dynamodb_table=os.getenv("DYNAMODB_TABLE", "documents"),
            sqs_queue_name=os.getenv("SQS_QUEUE_NAME", "document-events"),
        )
