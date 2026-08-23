variable "alarm_email" {
  type        = string
  description = "Email for CloudWatch alarm notifications."
}

variable "sqs_queue_name" {
  type        = string
  description = "Name of the main SQS queue."
}

variable "sqs_dlq_name" {
  type        = string
  description = "Name of the dead letter queue."
}

variable "lambda_function_name" {
  type        = string
  description = "Name of the Lambda function to monitor."
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to all resources."
}

variable "region" {
  type        = string
  description = "AWS region for dashboard metrics."
}
