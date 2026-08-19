output "function_name" {
  description = "Lambda function name."
  value       = aws_lambda_function.document_processor.function_name
}

output "function_arn" {
  description = "Lambda function ARN."
  value       = aws_lambda_function.document_processor.arn
}

output "invoke_arn" {
  description = "Lambda invoke ARN."
  value       = aws_lambda_function.document_processor.invoke_arn
}

output "esm_uuid" {
  description = "Event source mapping UUID."
  value       = aws_lambda_event_source_mapping.sqs_to_lambda.uuid
}
