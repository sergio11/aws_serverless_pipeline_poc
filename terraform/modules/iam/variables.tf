variable "name_prefix" {
  type        = string
  description = "Prefix used to name the IAM role."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the IAM role."
  default     = {}
}
