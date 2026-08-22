variable "name_prefix" {
  type        = string
  description = "Prefix used to name the IAM role."
}

variable "s3_bucket_arn" {
  type        = string
  description = "ARN of the S3 bucket the Lambda reads from."
}

variable "dynamodb_table_arn" {
  type        = string
  description = "ARN of the DynamoDB table the Lambda accesses."
}

variable "sqs_queue_arn" {
  type        = string
  description = "ARN of the SQS queue the Lambda reads from."
}

variable "sqs_dlq_arn" {
  type        = string
  description = "ARN of the SQS dead-letter queue."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the IAM role."
  default     = {}
}
