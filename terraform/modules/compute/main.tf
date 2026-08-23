resource "aws_lambda_function" "document_processor" {
  function_name                = var.function_name
  role                         = var.lambda_role_arn
  handler                      = var.handler
  runtime                      = var.runtime
  timeout                      = var.timeout
  memory_size                  = var.memory_size
  reserved_concurrent_executions = 5

  s3_bucket = var.s3_bucket
  s3_key    = var.s3_key

  environment {
    variables = var.environment_variables
  }

  tags = var.tags
}

resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn = var.sqs_queue_arn
  function_name    = aws_lambda_function.document_processor.arn
  batch_size       = var.sqs_batch_size
  enabled          = true

  function_response_types = ["ReportBatchItemFailures"]
}
