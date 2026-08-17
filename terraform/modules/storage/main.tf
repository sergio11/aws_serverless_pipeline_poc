resource "aws_s3_bucket" "documents" {
  bucket = var.bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_ownership_controls" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}
