# ==============================================================================
# Terraform Configuration: Dev Environment
# ==============================================================================
# Orchestrates all CloudSweep infrastructure for the dev environment.
#
# Resources created:
#   1. State Tracker     — DynamoDB table for idempotent resource-scan state.
#   2. Smoke Lambda      — Phase 1 smoke handler (kept for regression testing).
#   3. Scan Lambda       — Scans for idle / orphaned AWS resources.
#   4. Evaluate Lambda   — Classifies findings as AUTO_REMEDIATE / NEEDS_APPROVAL.
#   5. Remediate Lambda  — Executes cleanup actions (snapshot + delete/stop/release).
#   6. Notify Lambda     — Sends Slack Block Kit messages (approval + summaries).
#   7. Approval Lambda   — Handles Slack interactive-component callbacks (Phase 4).
#   8. CloudSweep State Machine — Full PRD flow wired to all Lambdas.
#   9. Approval API      — API Gateway endpoint for Slack callbacks.
#  10. Scheduler         — EventBridge Scheduler triggers the state machine daily.
#
# Architecture:
#   Scheduler → State Machine → Scan → Evaluate → Decision
#                                  ↓ AUTO_REMEDIATE          ↓ NEEDS_APPROVAL
#                               Remediate              WaitForApproval (24 h)
#                                  └── NotifyComplete      ↓ approve / deny / timeout
#                                                       Remediate / RecordDenial / RecordTimeout
#                               NotifyNoFindings (no findings path)
# ==============================================================================

# ------------------------------------------------------------------------------
# State Tracker Module
# ------------------------------------------------------------------------------
# DynamoDB table used by all Lambdas for idempotent state tracking.
# ------------------------------------------------------------------------------

module "state_tracker" {
  source     = "../../modules/state-tracker"
  table_name = "${var.project_name}-state"
}

# ------------------------------------------------------------------------------
# Smoke Lambda Module (Phase 1 — kept for regression smoke tests)
# ------------------------------------------------------------------------------

module "smoke_lambda" {
  source        = "../../modules/lambda"
  function_name = "${var.project_name}-smoke"
  description   = "Phase 1 smoke handler"
  handler       = "python.handler.lambda_handler"
  source_path   = abspath("${path.module}/${var.lambda_source_path}")


  environment_variables = {
    POWERTOOLS_SERVICE_NAME = "cloudsweep"
    CLOUDSWEEP_DRY_RUN      = "true"
    STATE_TABLE_NAME        = module.state_tracker.table_name
  }

  additional_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
      Resource = [module.state_tracker.table_arn, "${module.state_tracker.table_arn}/index/*"]
    }]
  })
}

# ------------------------------------------------------------------------------
# Scan Lambda Module
# ------------------------------------------------------------------------------
# Invoked as the first Step Functions state. Calls all four resource scanners
# (EBS, RDS, EIP, Snapshot) and returns a normalised findings list.
# ------------------------------------------------------------------------------

module "scan_lambda" {
  source        = "../../modules/lambda"
  function_name = "${var.project_name}-scan"
  description   = "CloudSweep scan Lambda — detects idle and orphaned resources"
  handler       = "python.handler.scan_handler"
  source_path   = abspath("${path.module}/${var.lambda_source_path}")
  timeout       = 300


  environment_variables = {
    POWERTOOLS_SERVICE_NAME = "cloudsweep"
    CLOUDSWEEP_DRY_RUN      = "true"
    STATE_TABLE_NAME        = module.state_tracker.table_name
    # LAB. Default 7 days too long for same-day Cost Detective walkthrough.
    # Drop to 0 so freshly-seeded zombie volumes register immediately.
    # Revert to "7" (or remove) for production-like CloudSweep behaviour.
    EBS_GRACE_DAYS = "0"
  }

  additional_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [module.state_tracker.table_arn, "${module.state_tracker.table_arn}/index/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeVolumes",
          "ec2:DescribeSnapshots",
          "ec2:DescribeAddresses",
          "rds:DescribeDBInstances",
          "cloudwatch:GetMetricStatistics",
        ]
        Resource = "*"
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# Evaluate Lambda Module
# ------------------------------------------------------------------------------
# Receives the scan findings, classifies each as AUTO_REMEDIATE or
# NEEDS_APPROVAL, and returns a decision + classified findings list.
# ------------------------------------------------------------------------------

module "evaluate_lambda" {
  source        = "../../modules/lambda"
  function_name = "${var.project_name}-evaluate"
  description   = "CloudSweep evaluate Lambda — classifies findings for routing"
  handler       = "python.evaluator.handler"
  source_path   = abspath("${path.module}/${var.lambda_source_path}")


  environment_variables = {
    POWERTOOLS_SERVICE_NAME = "cloudsweep"
    CLOUDSWEEP_DRY_RUN      = "true"
    STATE_TABLE_NAME        = module.state_tracker.table_name
    APPROVAL_THRESHOLD_USD  = "500"
  }

  additional_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
      Resource = [module.state_tracker.table_arn, "${module.state_tracker.table_arn}/index/*"]
    }]
  })
}

# ------------------------------------------------------------------------------
# Remediate Lambda Module
# ------------------------------------------------------------------------------
# Performs the actual cleanup actions: snapshot + delete EBS, stop RDS,
# release EIP, delete stale snapshot.  Respects dry-run mode.
# ------------------------------------------------------------------------------

module "remediate_lambda" {
  source        = "../../modules/lambda"
  function_name = "${var.project_name}-remediate"
  description   = "CloudSweep remediate Lambda — performs cleanup actions"
  handler       = "python.remediator.handler"
  source_path   = abspath("${path.module}/${var.lambda_source_path}")
  timeout       = 300


  environment_variables = {
    POWERTOOLS_SERVICE_NAME = "cloudsweep"
    CLOUDSWEEP_DRY_RUN      = "true"
    STATE_TABLE_NAME        = module.state_tracker.table_name
  }

  additional_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [module.state_tracker.table_arn, "${module.state_tracker.table_arn}/index/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DeleteVolume",
          "ec2:CreateSnapshot",
          "ec2:ReleaseAddress",
          "ec2:DeleteSnapshot",
          "rds:StopDBInstance",
          "rds:CreateDBSnapshot",
        ]
        Resource = "*"
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# Notify Lambda Module
# ------------------------------------------------------------------------------
# Sends Slack Block Kit messages for every terminal path in the workflow:
# NEEDS_APPROVAL (with task token + buttons), COMPLETE, TIMEOUT, DENIED,
# NO_FINDINGS.  Webhook URL is loaded from SSM at runtime.
# ------------------------------------------------------------------------------

module "notify_lambda" {
  source        = "../../modules/lambda"
  function_name = "${var.project_name}-notify"
  description   = "CloudSweep notify Lambda — sends Slack Block Kit messages"
  handler       = "python.notifier.handler"
  source_path   = abspath("${path.module}/${var.lambda_source_path}")


  environment_variables = {
    POWERTOOLS_SERVICE_NAME      = "cloudsweep"
    STATE_TABLE_NAME             = module.state_tracker.table_name
    SLACK_WEBHOOK_PARAMETER_NAME = "/cloudsweep/slack/webhook"
  }

  additional_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [module.state_tracker.table_arn, "${module.state_tracker.table_arn}/index/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/cloudsweep/slack/webhook"
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# Approval Lambda Module
# ------------------------------------------------------------------------------
# API Gateway Lambda — validates Slack HMAC-SHA256 signatures, calls
# Step Functions SendTaskSuccess / SendTaskFailure, and writes DynamoDB audit
# records.  Signing secret is loaded from SSM at runtime.
# ------------------------------------------------------------------------------

module "approval_lambda" {
  source        = "../../modules/lambda"
  function_name = "${var.project_name}-approval"
  description   = "CloudSweep approval Lambda — handles Slack interactive callbacks"
  handler       = "python.approval.handler"
  source_path   = abspath("${path.module}/${var.lambda_source_path}")


  environment_variables = {
    POWERTOOLS_SERVICE_NAME             = "cloudsweep"
    STATE_TABLE_NAME                    = module.state_tracker.table_name
    SLACK_SIGNING_SECRET_PARAMETER_NAME = "/cloudsweep/slack/signing-secret"
  }

  additional_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [module.state_tracker.table_arn, "${module.state_tracker.table_arn}/index/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/cloudsweep/slack/signing-secret"
      },
      {
        Effect   = "Allow"
        Action   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
        Resource = "*"
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# CloudSweep State Machine (Full Phase 4 PRD Flow)
# ------------------------------------------------------------------------------
# Replaces the smoke-path state machine with the full
# SCAN → EVALUATE → DECISION → (WaitForApproval | REMEDIATE) → NOTIFY flow.
# ------------------------------------------------------------------------------

module "cloudsweep_state_machine" {
  source     = "../../modules/step-functions"
  name       = "${var.project_name}-cloudsweep"
  definition = jsonencode(local.cloudsweep_state_machine)

  lambda_function_arns = [
    module.scan_lambda.function_arn,
    module.evaluate_lambda.function_arn,
    module.remediate_lambda.function_arn,
    module.notify_lambda.function_arn,
  ]
}

# ------------------------------------------------------------------------------
# Approval API Module (Phase 4)
# ------------------------------------------------------------------------------
# Exposes POST /approval/callback through API Gateway so Slack interactive
# button clicks can resume the Step Functions waitForTaskToken workflow.
# ------------------------------------------------------------------------------

module "approval_api" {
  source               = "../../modules/approval-api"
  name                 = "${local.name_prefix}-approval-api"
  approval_lambda_arn  = module.approval_lambda.function_arn
  approval_lambda_name = module.approval_lambda.function_name
  tags                 = local.common_tags
}

# ------------------------------------------------------------------------------
# Scheduler Module
# ------------------------------------------------------------------------------
# EventBridge Scheduler triggers the full CloudSweep state machine on the
# configured cron expression (default: rate(1 day)).
# ------------------------------------------------------------------------------

module "scheduler" {
  source              = "../../modules/scheduler"
  name                = "${var.project_name}-scheduler"
  schedule_expression = var.schedule_expression
  state_machine_arn   = module.cloudsweep_state_machine.state_machine_arn
}

# ------------------------------------------------------------------------------
# Smoke State Machine (Phase 1 — kept for regression testing only)
# ------------------------------------------------------------------------------

module "smoke_state_machine" {
  source               = "../../modules/step-functions"
  name                 = "${var.project_name}-smoke-sfn"
  definition           = jsonencode(local.smoke_state_machine)
  lambda_function_arns = [module.smoke_lambda.function_arn]
}

# ==============================================================================
# LAB — Cost Detective Audit Sandbox Waste
# ==============================================================================
# Opt-in zombie-asset generator. Disabled by default; deploy with:
#   terraform apply -var="enable_lab_seed=true" -var="lab_owner_email=<you>"
#
# Tagged CostCenter=<var.lab_cost_center> so the EBS garbage collector and the
# tag-governance module can filter on lab-only resources without touching the
# CloudSweep stack.
# ==============================================================================

module "lab_seed" {
  count  = var.enable_lab_seed ? 1 : 0
  source = "../../modules/lab-seed"

  name_prefix           = "${var.project_name}-lab"
  cost_center           = var.lab_cost_center
  owner                 = var.lab_owner_email
  idle_instance_type    = var.lab_idle_instance_type
  ebs_availability_zone = var.lab_availability_zone
  vpc_id                = var.lab_vpc_id
  subnet_id             = var.lab_subnet_id
}

# ==============================================================================
# LAB - Cost Detective Audit Active Cost Controls
# ==============================================================================
# Opt-in AWS Budget + SNS email alert. Disabled by default; deploy with:
#   terraform apply -var="enable_lab_budget=true" -var="lab_budget_email=<you>"
# Subscription email requires a one-time confirmation click before alerts flow.
# ==============================================================================

module "lab_budget" {
  count  = var.enable_lab_budget ? 1 : 0
  source = "../../modules/lab-budgets-sns"

  name_prefix              = "${var.project_name}-lab"
  budget_limit_usd         = var.lab_budget_limit_usd
  actual_threshold_percent = var.lab_budget_actual_threshold_percent
  subscriber_email         = var.lab_budget_email

  tags = {
    CostCenter = var.lab_cost_center
    Project    = "cost-detective"
    ManagedBy  = "terraform"
  }
}

# ==============================================================================
# LAB - Cost Detective Audit CostCenter Tag Governance
# ==============================================================================
# Opt-in IAM deny policy (preventive) + optional AWS Config rule (detective).
# Default off; deploy with:
#   terraform apply -var="enable_lab_tag_governance=true"
# Optionally enable Config rule with -var="lab_enable_config_rule=true".
# ==============================================================================

module "lab_tag_governance" {
  count  = var.enable_lab_tag_governance ? 1 : 0
  source = "../../modules/lab-tag-governance"

  name_prefix            = "${var.project_name}-lab"
  required_tag_key       = var.lab_required_tag_key
  enable_config_rule     = var.lab_enable_config_rule
  create_config_recorder = var.lab_create_config_recorder

  tags = {
    CostCenter = var.lab_cost_center
    Project    = "cost-detective"
    ManagedBy  = "terraform"
  }
}

# ==============================================================================
# LAB - Cost Detective Audit Optimization Architecture
# ==============================================================================
# Opt-in Mixed Instances + Spot Auto Scaling Group. Disabled by default;
# deploy with:
#   terraform apply -var="enable_lab_compute=true"
# ==============================================================================

module "lab_compute" {
  count  = var.enable_lab_compute ? 1 : 0
  source = "../../modules/lab-compute"

  name_prefix             = "${var.project_name}-lab"
  cost_center             = var.lab_cost_center
  owner                   = var.lab_owner_email
  instance_types          = var.lab_compute_instance_types
  on_demand_base_capacity = var.lab_compute_on_demand_base
  desired_capacity        = var.lab_compute_desired_capacity
  max_size                = var.lab_compute_max_size
}
