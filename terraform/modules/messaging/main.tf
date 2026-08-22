resource "aws_sqs_queue" "dlq" {
  name = var.dlq_name
  tags = var.tags

  # NOTE: KMS encryption is disabled for local Floci compatibility.
  # For AWS real, add: kms_master_key_id = "alias/aws/sqs"
}

resource "aws_sqs_queue" "documents" {
  name                       = var.queue_name
  visibility_timeout_seconds = 330
  tags                       = var.tags

  # NOTE: KMS encryption is disabled for local Floci compatibility.
  # For AWS real, add: kms_master_key_id = "alias/aws/sqs"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}
