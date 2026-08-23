resource "aws_cloudwatch_dashboard" "main" {
  count = var.enable_monitoring ? 1 : 0

  dashboard_name = "${var.lambda_function_name}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.sqs_queue_name]
          ]
          period = 300
          stat   = "Average"
          region = var.region
          title  = "SQS Queue Depth"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.sqs_dlq_name]
          ]
          period = 300
          stat   = "Average"
          region = var.region
          title  = "SQS DLQ Depth"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_function_name],
            ["AWS/Lambda", "Errors", "FunctionName", var.lambda_function_name]
          ]
          period = 300
          stat   = "Sum"
          region = var.region
          title  = "Lambda Invocations/Errors"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_function_name]
          ]
          period = 300
          stat   = "Average"
          region = var.region
          title  = "Lambda Duration"
        }
      }
    ]
  })
}

resource "aws_sns_topic" "alarm_notifications" {
  count = var.enable_monitoring ? 1 : 0
  name  = "${var.lambda_function_name}-alarm-notifications"
  tags  = var.tags
}

resource "aws_sns_topic_subscription" "alarm_email" {
  count     = var.enable_monitoring && var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarm_notifications[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  count               = var.enable_monitoring ? 1 : 0
  alarm_name          = "${var.lambda_function_name}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alarm when DLQ has messages"
  alarm_actions       = [aws_sns_topic.alarm_notifications[0].arn]
  ok_actions          = [aws_sns_topic.alarm_notifications[0].arn]
  tags                = var.tags

  dimensions = {
    QueueName = var.sqs_dlq_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count               = var.enable_monitoring ? 1 : 0
  alarm_name          = "${var.lambda_function_name}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alarm when Lambda has errors"
  alarm_actions       = [aws_sns_topic.alarm_notifications[0].arn]
  ok_actions          = [aws_sns_topic.alarm_notifications[0].arn]
  tags                = var.tags

  dimensions = {
    FunctionName = var.lambda_function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  count               = var.enable_monitoring ? 1 : 0
  alarm_name          = "${var.lambda_function_name}-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alarm when Lambda is throttled"
  alarm_actions       = [aws_sns_topic.alarm_notifications[0].arn]
  ok_actions          = [aws_sns_topic.alarm_notifications[0].arn]
  tags                = var.tags

  dimensions = {
    FunctionName = var.lambda_function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "sqs_depth_high" {
  count               = var.enable_monitoring ? 1 : 0
  alarm_name          = "${var.lambda_function_name}-sqs-depth-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 100
  alarm_description   = "Alarm when SQS queue depth exceeds 100"
  alarm_actions       = [aws_sns_topic.alarm_notifications[0].arn]
  ok_actions          = [aws_sns_topic.alarm_notifications[0].arn]
  tags                = var.tags

  dimensions = {
    QueueName = var.sqs_queue_name
  }
}
