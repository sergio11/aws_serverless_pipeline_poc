variable "function_name" {
  type        = string
  description = "Lambda function name."
}

variable "lambda_role_arn" {
  type        = string
  description = "IAM role ARN for the Lambda function."
}

variable "s3_bucket" {
  type        = string
  description = "S3 bucket containing the Lambda deployment package."
}

variable "s3_key" {
  type        = string
  description = "S3 key of the Lambda deployment package ZIP."
}

variable "handler" {
  type        = string
  description = "Lambda handler (module.function)."
  default     = "handler.lambda_handler"
}

variable "runtime" {
  type        = string
  description = "Lambda runtime identifier."
  default     = "python3.13"
}

variable "timeout" {
  type        = number
  description = "Lambda function timeout in seconds."
  default     = 30
}

variable "memory_size" {
  type        = number
  description = "Lambda function memory in MB."
  default     = 128
}

variable "environment_variables" {
  type        = map(string)
  description = "Environment variables for the Lambda function."
  default     = {}
}

variable "sqs_queue_arn" {
  type        = string
  description = "ARN of the SQS queue to connect as event source."
}

variable "sqs_batch_size" {
  type        = number
  description = "Maximum number of messages per Lambda invocation."
  default     = 1
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to supported resources."
  default     = {}
}
