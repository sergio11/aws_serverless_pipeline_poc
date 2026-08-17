resource "aws_dynamodb_table" "documents" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  tags         = var.tags

  attribute {
    name = "id"
    type = "S"
  }
}
