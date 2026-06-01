output "sns_topic_arn" {
  description = "ARN of the cost-alerts SNS topic."
  value       = aws_sns_topic.alerts.arn
}

output "sns_topic_name" {
  description = "Name of the cost-alerts SNS topic."
  value       = aws_sns_topic.alerts.name
}

output "subscription_arn" {
  description = "ARN of the email subscription. Will be 'PendingConfirmation' until the subscriber clicks the confirmation link."
  value       = aws_sns_topic_subscription.email.arn
}

output "budget_name" {
  description = "Name of the AWS Budget."
  value       = aws_budgets_budget.monthly.name
}

output "budget_id" {
  description = "ID of the AWS Budget."
  value       = aws_budgets_budget.monthly.id
}

output "subscriber_email" {
  description = "Email subscribed to alerts (requires confirmation)."
  value       = var.subscriber_email
}
