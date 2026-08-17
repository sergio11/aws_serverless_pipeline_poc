locals {
  name_prefix = "${var.project_name}-${var.environment}"

  bucket_name = "${local.name_prefix}-documents"
  table_name  = "documents"
  queue_name  = "document-events"
  dlq_name    = "document-events-dlq"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
