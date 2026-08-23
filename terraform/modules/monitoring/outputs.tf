output "dashboard_url" {
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
  description = "URL of the CloudWatch dashboard."
}

output "sns_topic_arn" {
  value       = aws_sns_topic.alarm_notifications.arn
  description = "ARN of the SNS topic for alarm notifications."
}
