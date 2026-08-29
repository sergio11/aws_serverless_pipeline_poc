provider "aws" {
  region                      = var.aws_region
  access_key                  = var.aws_access_key_id
  secret_key                  = var.aws_secret_access_key
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true

  skip_requesting_account_id = true

  skip_region_validation = true

  endpoints {
    cloudwatch = var.aws_endpoint
    dynamodb   = var.aws_endpoint
    events     = var.aws_endpoint
    iam        = var.aws_endpoint
    lambda     = var.aws_endpoint
    s3         = var.aws_endpoint
    scheduler  = var.aws_endpoint
    sqs        = var.aws_endpoint
    sts        = var.aws_endpoint
  }
}
