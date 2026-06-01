# ==============================================================================
# Terraform Module: API Gateway — Slack Approval Callback
# ==============================================================================
# This module exposes a single endpoint:
#
#   POST /approval/callback
#
# Slack interactive component events (button clicks on Approve / Deny) are
# forwarded here.  API Gateway proxies the raw request to the approval Lambda
# (AWS_PROXY integration) which validates the Slack HMAC-SHA256 signature and
# calls Step Functions SendTaskSuccess or SendTaskFailure.
#
# Resources:
#   1. aws_api_gateway_rest_api          — root REST API
#   2. aws_api_gateway_resource          — /approval resource
#   3. aws_api_gateway_resource          — /approval/callback resource
#   4. aws_api_gateway_method            — POST on /approval/callback
#   5. aws_api_gateway_integration       — AWS_PROXY to approval Lambda
#   6. aws_api_gateway_deployment        — deploys the API
#   7. aws_api_gateway_stage             — "v1" stage
#   8. aws_lambda_permission             — grants API GW permission to invoke Lambda
# ==============================================================================

# ------------------------------------------------------------------------------
# REST API
# ------------------------------------------------------------------------------
# Root of the API Gateway REST API.  All resources and methods are children of
# this resource.
# ------------------------------------------------------------------------------

resource "aws_api_gateway_rest_api" "this" {
  name        = var.name
  description = "CloudSweep approval callback API — receives Slack interactive events"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = var.tags
}

# ------------------------------------------------------------------------------
# /approval resource
# ------------------------------------------------------------------------------
# Parent path segment.  Contains the /callback child resource.
# ------------------------------------------------------------------------------

resource "aws_api_gateway_resource" "approval" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "approval"
}

# ------------------------------------------------------------------------------
# /approval/callback resource
# ------------------------------------------------------------------------------
# The Slack app's Interactivity & Shortcuts URL must be set to this path so
# that interactive component events (button clicks) are routed here.
# ------------------------------------------------------------------------------

resource "aws_api_gateway_resource" "callback" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.approval.id
  path_part   = "callback"
}

# ------------------------------------------------------------------------------
# POST /approval/callback method
# ------------------------------------------------------------------------------
# Authorization is NONE — the approval Lambda performs its own request
# authentication using Slack HMAC-SHA256 signature verification.
# ------------------------------------------------------------------------------

resource "aws_api_gateway_method" "post_callback" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.callback.id
  http_method   = "POST"
  authorization = "NONE"
}

# ------------------------------------------------------------------------------
# Lambda proxy integration
# ------------------------------------------------------------------------------
# AWS_PROXY passes the full API GW request envelope (headers, body, context)
# to the Lambda function and returns the Lambda response directly to the caller.
# ------------------------------------------------------------------------------

resource "aws_api_gateway_integration" "lambda_proxy" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.callback.id
  http_method             = aws_api_gateway_method.post_callback.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${var.approval_lambda_arn}/invocations"
}

# Current region data source (needed to construct the Lambda invocation URI)
data "aws_region" "current" {}

# ------------------------------------------------------------------------------
# API Gateway deployment
# ------------------------------------------------------------------------------
# Must be recreated whenever the API definition changes.  The triggers map
# captures the method and integration IDs so Terraform detects changes
# automatically.
# ------------------------------------------------------------------------------

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  # Ensure the method + integration exist before deploying.
  depends_on = [
    aws_api_gateway_method.post_callback,
    aws_api_gateway_integration.lambda_proxy,
  ]

  # Force a new deployment when any method or integration changes.
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.approval.id,
      aws_api_gateway_resource.callback.id,
      aws_api_gateway_method.post_callback.id,
      aws_api_gateway_integration.lambda_proxy.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ------------------------------------------------------------------------------
# API Gateway stage
# ------------------------------------------------------------------------------
# Deploys the API to the "v1" stage.  The invoke URL exposed by this stage is
# the value that should be configured in the Slack app.
# ------------------------------------------------------------------------------

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = "v1"

  tags = var.tags
}

# ------------------------------------------------------------------------------
# Lambda invoke permission
# ------------------------------------------------------------------------------
# Grants API Gateway permission to invoke the approval Lambda.  The source ARN
# is scoped to the specific REST API so other API GW deployments in the same
# account cannot trigger this Lambda.
# ------------------------------------------------------------------------------

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.approval_lambda_name
  principal     = "apigateway.amazonaws.com"

  # Scope to this specific API and all its stages/methods.
  source_arn = "${aws_api_gateway_rest_api.this.execution_arn}/*/*"
}
