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

module "iam" {
  source = "./modules/iam"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "compute" {
  source = "./modules/compute"

  function_name   = local.lambda_function_name
  lambda_role_arn = module.iam.role_arn
  s3_bucket       = module.storage.bucket_name
  s3_key          = "lambda/document-processor.zip"
  handler         = "handler.lambda_handler"
  runtime         = "python3.13"
  timeout         = 30
  memory_size     = 128
  sqs_queue_arn   = module.messaging.queue_arn
  sqs_batch_size  = 10
  environment_variables = {
    AWS_ENDPOINT_URL   = "http://floci:4566"
    AWS_DEFAULT_REGION = "eu-west-1"
    DYNAMODB_TABLE     = local.table_name
    SQS_QUEUE_NAME     = local.queue_name
  }
  tags = local.common_tags
}
