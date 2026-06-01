# ==============================================================================
# Terraform Configuration: Production Environment
# ==============================================================================
# This file defines the core infrastructure components for the CloudSweep
# production environment. It orchestrates the creation of:
#
# 1. State Tracker: DynamoDB table for tracking resource scan state
#    - Enables idempotent scanning by recording processed resources
#    - Uses composite key (resource_id + scan_date) for uniqueness
#    - GSI on resource_type for efficient type-based queries
#
# 2. Smoke Lambda: Python handler for initial smoke testing
#    - Zipped and deployed as AWS Lambda function
#    - Configured with Powertools for structured logging
#    - Dry-run mode enabled for safe testing
#    - Writes scan state to the state tracker table
#
# 3. Smoke State Machine: Step Functions workflow for Lambda orchestration
#    - Invokes the smoke Lambda function
#    - Logs full execution data to CloudWatch
#    - IAM role grants invoke permission on the Lambda
#
# 4. Scheduler: EventBridge schedule for automated triggering
#    - Runs the smoke state machine on a configurable schedule
#    - Default: daily execution (rate(1 day))
#    - Passes event source and mode to the state machine
#
# Architecture:
#   Scheduler (EventBridge) --> State Machine (Step Functions) --> Lambda
#                                                                      |
#                                                                      v
#                                                              State Tracker
#                                                                 (DynamoDB)
#
# Note: This configuration mirrors the dev environment. For production,
# consider adjusting: schedule frequency, memory allocation, retention
# periods, and enabling DLQ for failed executions.
# ==============================================================================

# ------------------------------------------------------------------------------
# State Tracker Module
# ------------------------------------------------------------------------------
# Provisions a DynamoDB table for tracking processed resources.
# Used by Lambda functions to implement idempotent scanning.
# ------------------------------------------------------------------------------

module "state_tracker" {
  source     = "../../modules/state-tracker"
  table_name = "${var.project_name}-state"
}

# ------------------------------------------------------------------------------
# Smoke Lambda Module
# ------------------------------------------------------------------------------
# Creates the main Lambda function that handles smoke test operations.
# - Source code packaged from: ../../../src/python (configurable)
# - Handler: handler.lambda_handler (configurable)
# - Runtime: Python 3.9+ (configurable via variables)
# - Environment variables configure CloudSweep behavior:
#   - POWERTOOLS_SERVICE_NAME: Logging service identifier
#   - CLOUDSWEEP_DRY_RUN: Prevents actual resource modification
#   - STATE_TABLE_NAME: DynamoDB table for state tracking
# ------------------------------------------------------------------------------

module "smoke_lambda" {
  source        = "../../modules/lambda"
  function_name = "${var.project_name}-smoke"
  description   = "Phase 1 smoke handler"
  handler       = "handler.lambda_handler"
  source_path   = abspath("${path.module}/${var.lambda_source_path}")

  environment_variables = {
    POWERTOOLS_SERVICE_NAME = "cloudsweep"
    CLOUDSWEEP_DRY_RUN      = "true"
    STATE_TABLE_NAME        = module.state_tracker.table_name
  }
}

# ------------------------------------------------------------------------------
# Smoke State Machine Module
# ------------------------------------------------------------------------------
# Creates a Step Functions state machine that orchestrates the smoke Lambda.
# - Definition: JSON-encoded ASL (Amazon States Language) workflow
# - Default workflow: Single Lambda invocation with event payload
# - Logging: Full execution data with 14-day retention
# - IAM: Role with permission to invoke the Lambda function
# ------------------------------------------------------------------------------

module "smoke_state_machine" {
  source               = "../../modules/step-functions"
  name                 = "${var.project_name}-smoke"
  definition           = jsonencode(local.smoke_state_machine)
  lambda_function_arns = [module.smoke_lambda.function_arn]
}

# ------------------------------------------------------------------------------
# Scheduler Module
# ------------------------------------------------------------------------------
# Creates an EventBridge Scheduler to trigger the state machine.
# - Schedule expression: Configurable (default: daily)
# - Target: Step Functions state machine ARN
# - IAM role: Permissions to start state machine executions
# - Input payload: Event source and mode passed to Lambda
# ------------------------------------------------------------------------------

module "scheduler" {
  source              = "../../modules/scheduler"
  name                = "${var.project_name}-scheduler"
  schedule_expression = var.schedule_expression
  state_machine_arn   = module.smoke_state_machine.state_machine_arn
}