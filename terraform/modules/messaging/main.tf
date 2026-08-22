resource "aws_sqs_queue" "dlq" {
  name                              = var.dlq_name
  kms_master_key_id                 = "alias/aws/sqs"
  kms_data_key_reuse_period_seconds = 300
  tags                              = var.tags
}

resource "aws_sqs_queue" "documents" {
  name                              = var.queue_name
  visibility_timeout_seconds        = 330
  kms_master_key_id                 = "alias/aws/sqs"
  kms_data_key_reuse_period_seconds = 300
  tags                              = var.tags

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}
