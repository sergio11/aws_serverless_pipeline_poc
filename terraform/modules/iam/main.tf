data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_worker" {
  statement {
    sid       = "S3ReadDocument"
    actions   = ["s3:GetObject"]
    resources = ["${var.s3_bucket_arn}/documents/*"]
  }

  statement {
    sid       = "S3DeleteDocument"
    actions   = ["s3:DeleteObject"]
    resources = ["${var.s3_bucket_arn}/documents/*"]
  }

  statement {
    sid = "DynamoDBAccess"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [var.dynamodb_table_arn]
  }

  statement {
    sid = "SQSAccess"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueUrl",
    ]
    resources = [
      var.sqs_queue_arn,
    ]
  }

  statement {
    sid = "SQSDLQAccess"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:GetQueueUrl",
    ]
    resources = [
      var.sqs_dlq_arn,
    ]
  }
}

resource "aws_iam_policy" "lambda_worker" {
  name   = "${var.name_prefix}-lambda-worker-policy"
  policy = data.aws_iam_policy_document.lambda_worker.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_worker" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_worker.arn
}
