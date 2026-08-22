resource "aws_sqs_queue" "dlq" {
  name = var.dlq_name
  tags = var.tags
}

resource "aws_sqs_queue" "documents" {
  name                       = var.queue_name
  visibility_timeout_seconds = 330
  tags                       = var.tags

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}
