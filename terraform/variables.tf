variable "aws_region" {
  type        = string
  description = "AWS region used by local-compatible clients."
  default     = "eu-west-1"
}

variable "aws_endpoint" {
  type        = string
  description = "Local AWS-compatible endpoint exposed by Floci."
  default     = "http://localhost:4566"
}

variable "aws_access_key_id" {
  type        = string
  description = "Dummy AWS access key for local emulation."
  default     = "test"
}

variable "aws_secret_access_key" {
  type        = string
  description = "Dummy AWS secret key for local emulation."
  default     = "test"
  sensitive   = true
}

variable "environment" {
  type        = string
  description = "Environment name used for local resource naming."
  default     = "local"
}

variable "project_name" {
  type        = string
  description = "Short project name used as resource prefix."
  default     = "poc"
}

variable "api_endpoint" {
  type        = string
  description = "Local backend API endpoint shown as Terraform output."
  default     = "http://localhost:8000"
}

variable "lambda_aws_endpoint_url" {
  type        = string
  description = "AWS endpoint URL used inside Lambda function containers."
  default     = "http://floci:4566"
}

variable "alarm_email" {
  type        = string
  description = "Email for CloudWatch alarm notifications."
  default     = ""
}
