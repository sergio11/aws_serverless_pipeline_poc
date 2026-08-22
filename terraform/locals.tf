locals {
  name_prefix = "${var.project_name}-${var.environment}"

  bucket_name = "${local.name_prefix}-documents"
  table_name  = "${local.name_prefix}-documents"
  queue_name  = "${local.name_prefix}-document-events"
  dlq_name    = "${local.name_prefix}-document-events-dlq"

  lambda_function_name = "${local.name_prefix}-document-processor"
  lambda_s3_key        = "lambda/document-processor.zip"
  lambda_handler       = "handler.lambda_handler"
  lambda_timeout       = 30
  lambda_memory_size   = 128

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
