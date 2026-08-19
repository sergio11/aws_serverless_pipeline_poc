output "api_endpoint" {
  description = "Local backend API endpoint."
  value       = var.api_endpoint
}

output "s3_bucket" {
  description = "Document object storage bucket name."
  value       = module.storage.bucket_name
}

output "dynamodb_table" {
  description = "Document metadata DynamoDB table name."
  value       = module.database.table_name
}

output "sqs_queue_url" {
  description = "Document events SQS queue URL."
  value       = module.messaging.queue_url
}

output "sqs_dlq_url" {
  description = "Document events dead-letter queue URL."
  value       = module.messaging.dlq_url
}

output "lambda_function_name" {
  description = "Lambda function name."
  value       = module.compute.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN."
  value       = module.compute.function_arn
}

output "lambda_esm_uuid" {
  description = "SQS-to-Lambda event source mapping UUID."
  value       = module.compute.esm_uuid
}
