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
}

resource "aws_lambda_function" "reconciler" {
  count                        = var.reconciler_function_name != "" ? 1 : 0
  function_name                = var.reconciler_function_name
  role                         = var.lambda_role_arn
  handler                      = var.reconciler_handler
  runtime                      = var.runtime
  timeout                      = var.timeout
  memory_size                  = var.memory_size
  reserved_concurrent_executions = 2

  s3_bucket = var.s3_bucket
  s3_key    = var.s3_key

  environment {
    variables = var.reconciler_environment_variables
  }

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "reconciler_schedule" {
  count               = var.reconciler_function_name != "" ? 1 : 0
  name                = "${var.reconciler_function_name}-rule"
  schedule_expression = var.reconciler_schedule_expression
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "reconciler_target" {
  count = var.reconciler_function_name != "" ? 1 : 0
  rule  = aws_cloudwatch_event_rule.reconciler_schedule[0].name
  arn   = aws_lambda_function.reconciler[0].arn
}

resource "aws_lambda_permission" "allow_eventbridge_to_call_reconciler" {
  count         = var.reconciler_function_name != "" ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reconciler[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.reconciler_schedule[0].arn
}
