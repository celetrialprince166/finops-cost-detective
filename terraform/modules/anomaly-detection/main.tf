# ==============================================================================
# Terraform Module: Anomaly Detection
# ==============================================================================
# Provisions AWS Cost Anomaly Detection monitor and subscription.
# ==============================================================================

variable "monitor_name" {
  description = "Name for the Cost Anomaly Detection monitor"
  type        = string
  default     = "cloudsweep-monitor"
}

variable "subscription_name" {
  description = "Name for the anomaly subscription"
  type        = string
  default     = "cloudsweep-alerts"
}

variable "alert_email" {
  description = "Email address for anomaly alerts"
  type        = string
  default     = "team@example.com"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

# ------------------------------------------------------------------------------
# Cost Anomaly Detection Monitor
# ------------------------------------------------------------------------------

resource "aws_ce_anomaly_monitor" "this" {
  name         = var.monitor_name
  monitor_type = "DIMENSIONAL"

  tags = var.tags
}

# ------------------------------------------------------------------------------
# Cost Anomaly Subscription
# ------------------------------------------------------------------------------

resource "aws_ce_anomaly_subscription" "this" {
  name             = var.subscription_name
  monitor_arn_list = [aws_ce_anomaly_monitor.this.arn]
  frequency        = "DAILY"

  subscriber {
    type    = "EMAIL"
    address = var.alert_email
  }

  tags = var.tags
}

# ------------------------------------------------------------------------------
# Outputs
# ------------------------------------------------------------------------------

output "monitor_arn" {
  description = "ARN of the Cost Anomaly Detection monitor"
  value       = aws_ce_anomaly_monitor.this.arn
}

output "subscription_arn" {
  description = "ARN of the anomaly subscription"
  value       = aws_ce_anomaly_subscription.this.arn
}