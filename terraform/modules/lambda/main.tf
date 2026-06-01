# ==============================================================================
# Terraform Module: AWS Lambda Function
# ==============================================================================
# This module provisions an AWS Lambda function with:
# - ZIP archive packaging from source directory
# - IAM role with basic execution and X-Ray tracing
# - Optional Dead Letter Queue (SQS) for failed invocations
# - Active tracing mode for detailed execution monitoring
# - Configurable runtime, timeout, and memory settings
# ==============================================================================

locals {
  # Directory where pip deps + source are assembled before zipping.
  pkg_dir = "${path.module}/build/${var.function_name}/pkg"
}

# Build the deployment package:
#   1. pip install aws-lambda-powertools (not in Lambda Python 3.12 runtime)
#   2. Copy project source on top
# Re-runs only when source file hashes change.
resource "null_resource" "build_package" {
  triggers = {
    source_hash = sha256(join(",", sort([
      for f in fileset(var.source_path, "**/*.py") :
      "${f}:${filesha256("${var.source_path}/${f}")}"
    ])))
  }

  provisioner "local-exec" {
    interpreter = ["PowerShell", "-Command"]
    command     = <<-PS1
      if (Test-Path '${local.pkg_dir}') { Remove-Item -Recurse -Force '${local.pkg_dir}' }
      New-Item -ItemType Directory -Force -Path '${local.pkg_dir}' | Out-Null
      py -m pip install aws-lambda-powertools aws-xray-sdk -t '${local.pkg_dir}' --quiet
      Copy-Item -Path '${var.source_path}/*' -Destination '${local.pkg_dir}' -Recurse -Force
    PS1
  }
}

# Zip the assembled package directory for Lambda deployment.
data "archive_file" "package" {
  type        = "zip"
  source_dir  = local.pkg_dir
  output_path = "${path.module}/build/${var.function_name}.zip"
  depends_on  = [null_resource.build_package]
}

# IAM policy document for Lambda service assumption
# Allows the Lambda service to assume this role
data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ------------------------------------------------------------------------------
# Optional Dead Letter Queue (SQS)
# ------------------------------------------------------------------------------
# Created when create_dlq is true. Failed Lambda invocations that exceed
# the retry limit will send the event to this queue for later processing.
# Message retention set to 14 days (1209600 seconds).
# ------------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  count = var.create_dlq ? 1 : 0

  name                      = "${var.function_name}-dlq"
  message_retention_seconds = 1209600
}

# ------------------------------------------------------------------------------
# IAM Role for Lambda Execution
# ------------------------------------------------------------------------------
# Role that Lambda assumes at runtime. Attached policies provide:
# - AWSLambdaBasicExecutionRole: CloudWatch Logs write access
# - AWSXRayDaemonWriteAccess: X-Ray tracing data upload
# ------------------------------------------------------------------------------

resource "aws_iam_role" "this" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "xray" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# Grant the Lambda role permission to deliver failed invocations to its DLQ.
# Required: Lambda service calls sqs:SendMessage on the DLQ ARN at invocation time.
resource "aws_iam_role_policy" "dlq_send" {
  count = var.create_dlq ? 1 : 0

  name = "${var.function_name}-dlq-send"
  role = aws_iam_role.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.dlq[0].arn
      }
    ]
  })
}

# Application-level IAM permissions passed in by the calling environment.
# Each Lambda gets only the permissions it needs (least privilege).
resource "aws_iam_role_policy" "additional" {
  count = var.additional_policy_json != null ? 1 : 0

  name   = "${var.function_name}-additional"
  role   = aws_iam_role.this.id
  policy = var.additional_policy_json
}

# ------------------------------------------------------------------------------
# Lambda Function Resource
# ------------------------------------------------------------------------------
# Core Lambda function with configuration for:
# - Handler: Entry point function (e.g., handler.lambda_handler)
# - Runtime: Python version (default: python3.9)
# - Timeout: Maximum execution time (default: 30 seconds)
# - Memory: Memory allocation in MB (default: 128 MB)
# - Tracing: Active X-Ray mode for performance insights
# - Environment: Custom environment variables for configuration
# ------------------------------------------------------------------------------

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  description      = var.description
  role             = aws_iam_role.this.arn
  handler          = var.handler
  runtime          = var.runtime
  filename         = data.archive_file.package.output_path
  source_code_hash = data.archive_file.package.output_base64sha256
  timeout          = var.timeout
  memory_size      = var.memory_size

  # Dead Letter Queue configuration (conditional)
  # If enabled, failed invocations after retries go to SQS queue
  dynamic "dead_letter_config" {
    for_each = var.create_dlq ? [1] : []
    content {
      target_arn = aws_sqs_queue.dlq[0].arn
    }
  }

  # Enable X-Ray active tracing for detailed performance monitoring
  tracing_config {
    mode = "Active"
  }

  # Custom environment variables passed to the Lambda function
  environment {
    variables = var.environment_variables
  }

  # Ensure all IAM policies are attached before Lambda is created.
  # Without this, Lambda creation can race ahead of policy propagation.
  depends_on = [
    aws_iam_role_policy_attachment.basic_execution,
    aws_iam_role_policy_attachment.xray,
    aws_iam_role_policy.dlq_send,
    aws_iam_role_policy.additional,
  ]
}