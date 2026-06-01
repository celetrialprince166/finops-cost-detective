# ==============================================================================
# Terraform Module: EventBridge Scheduler
# ==============================================================================
# This module creates an EventBridge Scheduler for triggering state machine
# executions on a cron-based schedule. Includes:
# - IAM role for Scheduler to start Step Functions executions
# - Configurable schedule expression (rate-based or cron)
# - Flexible time window configuration
#
# Use Cases:
# - Scheduled cleanup jobs (daily, weekly, monthly)
# - Periodic compliance scans
# - Recurring data synchronization tasks
# ==============================================================================

# IAM policy document for EventBridge Scheduler service assumption
data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

# IAM policy for starting Step Functions state machine executions
# Grants permission to invoke the specific state machine ARN
data "aws_iam_policy_document" "start_execution" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [var.state_machine_arn]
  }
}

# ------------------------------------------------------------------------------
# IAM Role for Scheduler Execution
# ------------------------------------------------------------------------------
# Role assumed by EventBridge Scheduler when triggering the target.
# Has permission to start executions on the specified state machine.
# ------------------------------------------------------------------------------

resource "aws_iam_role" "this" {
  name               = "${var.name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "start_execution" {
  name   = "${var.name}-start-execution"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.start_execution.json
}

# ------------------------------------------------------------------------------
# EventBridge Scheduler Schedule
# ------------------------------------------------------------------------------
# Schedule configuration:
# - schedule_expression: Cron or rate expression (e.g., "rate(1 day)")
# - flexible_time_window: OFF disables the window, fixed window mode available
# - target: The state machine to invoke with optional input payload
#
# Example expressions:
# - "rate(1 day)" - Runs once per day
# - "rate(1 hour)" - Runs every hour
# - "cron(0 12 * * ? *)" - Runs daily at noon UTC
# ------------------------------------------------------------------------------

resource "aws_scheduler_schedule" "this" {
  name                = var.name
  schedule_expression = var.schedule_expression
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.state_machine_arn
    role_arn = aws_iam_role.this.arn
    input    = var.input
  }

  # Wait for the inline policy to be fully attached before creating the schedule.
  # EventBridge validates the role can call states:StartExecution at creation time.
  depends_on = [aws_iam_role_policy.start_execution]
}