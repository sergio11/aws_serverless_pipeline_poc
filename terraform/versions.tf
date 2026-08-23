terraform {
  required_version = ">= 1.8.0"

  # Para producción, descomentar y configurar:
  # backend "s3" {
  #   bucket         = "my-tf-state-bucket"
  #   key            = "poc-aws/terraform.tfstate"
  #   region         = "eu-west-1"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.53.0"
    }
  }
}
