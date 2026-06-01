# ==============================================================================
# Module: lab-budgets-sns
# ==============================================================================
# Cost Detective Audit - active cost control.
#
# Provisions:
#   1. SNS topic for cost alerts.
#   2. Email subscription to that topic.
#   3. Topic access policy granting budgets.amazonaws.com publish rights.
#   4. AWS Budget at var.budget_limit_usd (default $50/month) with:
#        - FORECASTED notification (>= forecasted_threshold_percent of budget).
#        - Optional ACTUAL notification (>= actual_threshold_percent of budget).
#
# Note: AWS Budgets is a global service but the Terraform provider creates the
# resource via the standard regional provider. The SNS topic is regional and
# lives in the provider's configured region.
# ==============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  topic_name  = "${var.name_prefix}-cost-alerts"
  budget_name = "${var.name_prefix}-monthly-budget"
}

# ------------------------------------------------------------------------------
# SNS topic
# ------------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = local.topic_name
  tags = merge(var.tags, { Name = local.topic_name })
}

# Grant AWS Budgets permission to publish to this topic.
data "aws_iam_policy_document" "alerts_topic_policy" {
  statement {
    sid    = "AllowBudgetsToPublish"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts_topic_policy.json
}

# ------------------------------------------------------------------------------
# Email subscription
# ------------------------------------------------------------------------------
# The subscriber must click the confirmation link in their inbox before any
# alert can be delivered. Terraform creates the subscription in
# "pending confirmation" state; subscriber confirmation is out-of-band.

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.subscriber_email
}

# ------------------------------------------------------------------------------
# AWS Budget
# ------------------------------------------------------------------------------

resource "aws_budgets_budget" "monthly" {
  name              = local.budget_name
  budget_type       = "COST"
  limit_amount      = tostring(var.budget_limit_usd)
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2025-01-01_00:00"

  dynamic "cost_filter" {
    for_each = var.cost_filters
    content {
      name   = cost_filter.key
      values = cost_filter.value
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = var.forecasted_threshold_percent
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_sns_topic_arns  = [aws_sns_topic.alerts.arn]
    subscriber_email_addresses = []
  }

  dynamic "notification" {
    for_each = var.actual_threshold_percent > 0 ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = var.actual_threshold_percent
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_sns_topic_arns  = [aws_sns_topic.alerts.arn]
      subscriber_email_addresses = []
    }
  }

  depends_on = [aws_sns_topic_policy.alerts]
}
