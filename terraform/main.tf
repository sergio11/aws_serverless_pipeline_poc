module "storage" {
  source = "./modules/storage"

  bucket_name = local.bucket_name
  tags        = local.common_tags
}

module "database" {
  source = "./modules/database"

  table_name = local.table_name
  tags       = local.common_tags
}

module "messaging" {
  source = "./modules/messaging"

  queue_name = local.queue_name
  dlq_name   = local.dlq_name
  tags       = local.common_tags
}
