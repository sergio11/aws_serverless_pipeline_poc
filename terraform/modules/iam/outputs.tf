output "role_arn" {
  description = "ARN of the Lambda execution IAM role."
  value       = aws_iam_role.lambda_exec.arn
}

output "role_name" {
  description = "Name of the Lambda execution IAM role."
  value       = aws_iam_role.lambda_exec.name
}
