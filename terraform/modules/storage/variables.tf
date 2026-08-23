variable "bucket_name" {
  type        = string
  description = "Name of the S3 bucket used for document storage."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to supported resources."
  default     = {}
}

variable "force_destroy" {
  type        = bool
  description = "Destroy bucket even if not empty (for local POC)."
  default     = false
}
