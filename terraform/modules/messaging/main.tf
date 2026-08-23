resource "aws_sqs_queue" "dlq" {
  name = var.dlq_name
  tags = var.tags

  # NOTE: Si Floci no soporta KMS, hacer este bloque condicional con count.
  kms_master_key_id                 = "alias/aws/sqs"
  kms_data_key_reuse_period_seconds = 300
}

resource "aws_sqs_queue" "documents" {
  name                       = var.queue_name
  visibility_timeout_seconds = 330
  tags                       = var.tags

  # NOTE: Si Floci no soporta KMS, hacer este bloque condicional con count.
  kms_master_key_id                 = "alias/aws/sqs"
  kms_data_key_reuse_period_seconds = 300

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}
