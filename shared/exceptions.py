class DocumentNotFoundError(Exception):
    """Raised when a document_id references a non-existent DynamoDB item.

    This is a terminal error -- the message will be retried by SQS and
    eventually moved to the DLQ after maxReceiveCount failures, because
    a missing document cannot become valid through retries.
    """
