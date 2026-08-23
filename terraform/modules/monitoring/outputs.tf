output "dashboard_url" {
  value       = var.enable_monitoring ? "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main[0].dashboard_name}" : ""
  description = "URL of the CloudWatch dashboard (empty if monitoring disabled)."
}

output "sns_topic_arn" {
  value       = var.enable_monitoring ? aws_sns_topic.alarm_notifications[0].arn : ""
  description = "ARN of the SNS topic for alarm notifications (empty if monitoring disabled)."
}
