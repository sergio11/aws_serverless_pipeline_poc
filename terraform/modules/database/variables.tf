variable "table_name" {
  type        = string
  description = "Name of the DynamoDB table used for document metadata."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to supported resources."
  default     = {}
}
