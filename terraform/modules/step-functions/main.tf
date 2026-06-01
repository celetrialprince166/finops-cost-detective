# ==============================================================================
# Terraform Module: AWS Step Functions State Machine
# ==============================================================================
# This module creates an AWS Step Functions state machine for orchestrating
# Lambda function executions. Includes:
# - IAM role for Step Functions to invoke Lambda
# - CloudWatch Logs for execution history and debugging
# - JSON-based state machine definition
#
# The state machine provides:
# - Serverless workflow orchestration
# - Built-in retry logic and error handling
# - Execution history and visual debugging
# ==============================================================================

# IAM policy for Step Functions service to assume the execution role
data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

# IAM policy granting permission to invoke Lambda functions
# This allows the state machine to call the Lambda functions it orchestrates
data "aws_iam_policy_document" "invoke_lambda" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = var.lambda_function_arns
  }
}

# ------------------------------------------------------------------------------
# IAM Role for State Machine Execution
# ------------------------------------------------------------------------------
# Role assumed by Step Functions when executing the state machine.
# Has permission to invoke the Lambda functions defined in the workflow.
# ------------------------------------------------------------------------------

resource "aws_iam_role" "this" {
  name               = "${var.name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "invoke_lambda" {
  name   = "${var.name}-invoke-lambda"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.invoke_lambda.json
}

# Step Functions requires explicit CloudWatch Logs permissions to deliver
# execution logs. These are not covered by any AWS managed policy.
resource "aws_iam_role_policy" "cloudwatch_logs" {
  name = "${var.name}-cloudwatch-logs"
  role = aws_iam_role.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutLogEvents",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# Step Functions State Machine
# ------------------------------------------------------------------------------
# Serverless workflow that orchestrates Lambda function executions.
# Configuration includes:
# - Logging: Full execution data sent to CloudWatch Logs
# - Logging Level: ALL captures input, output, and execution details
# - Retention: Logs kept for 14 days for debugging and auditing
# ------------------------------------------------------------------------------

resource "aws_sfn_state_machine" "this" {
  name       = var.name
  role_arn   = aws_iam_role.this.arn
  definition = var.definition

  logging_configuration {
    include_execution_data = true
    level                  = "ALL"
    log_destination        = "${aws_cloudwatch_log_group.this.arn}:*"
  }

  # Explicit dependency ensures IAM role policies are fully attached before
  # Step Functions attempts to assume the role and write to CloudWatch Logs.
  # Without this, IAM propagation delay causes assume-role failures.
  depends_on = [
    aws_iam_role_policy.invoke_lambda,
    aws_iam_role_policy.cloudwatch_logs,
  ]
}

# CloudWatch Logs group for state machine execution logs
# Provides detailed execution history for debugging and auditing
resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/vendedlogs/states/${var.name}"
  retention_in_days = 14
}