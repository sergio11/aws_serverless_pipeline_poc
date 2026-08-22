provider "aws" {
  region                      = var.aws_region
  access_key                  = var.aws_access_key_id
  secret_key                  = var.aws_secret_access_key
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true

  # WARNING: Requerido para Floci (localstack) ya que no maneja validación
  # de account_id. NO usar en producción con AWS real.
  # Si se necesita AWS real, eliminar esta línea y usar IAM roles o
  # variables de entorno para credenciales.
  skip_requesting_account_id = true

  skip_region_validation = true

  endpoints {
    dynamodb = var.aws_endpoint
    iam      = var.aws_endpoint
    lambda   = var.aws_endpoint
    s3       = var.aws_endpoint
    sqs      = var.aws_endpoint
    sts      = var.aws_endpoint
  }
}
