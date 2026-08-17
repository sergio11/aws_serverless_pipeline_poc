variable "queue_name" {
  type        = string
  description = "Name of the main SQS queue."
}

variable "dlq_name" {
  type        = string
  description = "Name of the SQS dead-letter queue."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to supported resources."
  default     = {}
}
