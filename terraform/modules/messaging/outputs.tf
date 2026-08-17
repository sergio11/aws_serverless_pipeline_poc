output "queue_url" {
  description = "Main queue URL."
  value       = aws_sqs_queue.documents.url
}

output "queue_arn" {
  description = "Main queue ARN."
  value       = aws_sqs_queue.documents.arn
}

output "dlq_url" {
  description = "Dead-letter queue URL."
  value       = aws_sqs_queue.dlq.url
}

output "dlq_arn" {
  description = "Dead-letter queue ARN."
  value       = aws_sqs_queue.dlq.arn
}
