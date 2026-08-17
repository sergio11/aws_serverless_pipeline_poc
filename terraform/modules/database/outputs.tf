output "table_name" {
  description = "Created DynamoDB table name."
  value       = aws_dynamodb_table.documents.name
}

output "table_arn" {
  description = "Created DynamoDB table ARN."
  value       = aws_dynamodb_table.documents.arn
}
