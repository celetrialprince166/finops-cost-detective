# ==============================================================================
# Local Values: Dev Environment
# ==============================================================================
# Defines inline values derived from other configuration inputs.
# Used to construct the Step Functions state machine definition.
#
# Phase 4: Full PRD flow — SCAN → EVALUATE → DECISION → WaitForApproval /
#          REMEDIATE → NOTIFY (with timeout and denial catch paths).
# ==============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  # Shared tag map applied to all taggable resources in this environment.
  common_tags = {
    Project     = "cloudsweep"
    Environment = "dev"
    ManagedBy   = "terraform"
  }

  # Friendly resource-name prefix used across all modules.
  name_prefix = var.project_name

  # --------------------------------------------------------------------------
  # Standard retry policy reused by every Task state.
  # --------------------------------------------------------------------------
  default_retry = [
    {
      ErrorEquals     = ["States.ALL"]
      IntervalSeconds = 2
      MaxAttempts     = 3
      BackoffRate     = 2
    }
  ]

  # --------------------------------------------------------------------------
  # Full Remediation State Machine Definition (Amazon States Language)
  # --------------------------------------------------------------------------
  # Phase 4 flow:
  #   Scan → Evaluate → Decision
  #     → WaitForApproval (NEEDS_APPROVAL path, .waitForTaskToken)
  #         → Remediate  (on approve)
  #         → RecordDenial (on deny / TaskFailed)
  #         → RecordTimeout (on HeartbeatTimeout)
  #     → Remediate (AUTO_REMEDIATE path)
  #     → NotifyNoFindings (no findings)
  #   Remediate → NotifyComplete
  # --------------------------------------------------------------------------

  cloudsweep_state_machine = {
    Comment = "CloudSweep — full PRD remediation flow (Phase 4)"
    StartAt = "Scan"

    States = {

      # ------------------------------------------------------------------ Scan
      Scan = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = module.scan_lambda.function_arn
          "Payload.$"    = "$"
        }
        ResultPath = "$.scan_result"
        Retry      = local.default_retry
        Next       = "Evaluate"
      }

      # -------------------------------------------------------------- Evaluate
      Evaluate = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = module.evaluate_lambda.function_arn
          "Payload.$"    = "$.scan_result.Payload"
        }
        ResultPath = "$.eval_result"
        Retry      = local.default_retry
        Next       = "Decision"
      }

      # -------------------------------------------------------------- Decision
      Decision = {
        Type = "Choice"
        Choices = [
          {
            Variable     = "$.eval_result.Payload.decision"
            StringEquals = "NEEDS_APPROVAL"
            Next         = "WaitForApproval"
          },
          {
            Variable     = "$.eval_result.Payload.decision"
            StringEquals = "AUTO_REMEDIATE"
            Next         = "Remediate"
          }
        ]
        Default = "NotifyNoFindings"
      }

      # -------------------------------------------------------- WaitForApproval
      # Uses the .waitForTaskToken integration pattern.
      # The task pauses until the API Gateway callback calls
      # SendTaskSuccess (approve) or SendTaskFailure (deny).
      # HeartbeatSeconds acts as the 24-hour approval timeout.
      WaitForApproval = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke.waitForTaskToken"
        Parameters = {
          "FunctionName" = module.notify_lambda.function_arn
          Payload = {
            "task_token.$" = "$$.Task.Token"
            "findings.$"   = "$.eval_result.Payload.findings"
            "decision.$"   = "$.eval_result.Payload.decision"
          }
        }
        HeartbeatSeconds = 86400
        ResultPath       = "$.approval_result"
        Next             = "Remediate"
        Catch = [
          {
            ErrorEquals = ["States.HeartbeatTimeout"]
            Next        = "RecordTimeout"
            ResultPath  = "$.error"
          },
          {
            ErrorEquals = ["States.TaskFailed"]
            Next        = "RecordDenial"
            ResultPath  = "$.error"
          }
        ]
      }

      # -------------------------------------------------------------- Remediate
      Remediate = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = module.remediate_lambda.function_arn
          "Payload.$"    = "$.eval_result.Payload"
        }
        ResultPath = "$.remediation_result"
        Retry      = local.default_retry
        Next       = "NotifyComplete"
      }

      # ----------------------------------------------------------- RecordTimeout
      RecordTimeout = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = module.notify_lambda.function_arn
          Payload = {
            event_type   = "TIMEOUT"
            "findings.$" = "$.eval_result.Payload.findings"
          }
        }
        ResultPath = null
        Next       = "WorkflowEnd"
      }

      # ------------------------------------------------------------ RecordDenial
      RecordDenial = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = module.notify_lambda.function_arn
          Payload = {
            event_type   = "DENIED"
            "findings.$" = "$.eval_result.Payload.findings"
            "error.$"    = "$.error"
          }
        }
        ResultPath = null
        Next       = "WorkflowEnd"
      }

      # --------------------------------------------------------- NotifyNoFindings
      NotifyNoFindings = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = module.notify_lambda.function_arn
          Payload = {
            event_type = "NO_FINDINGS"
          }
        }
        ResultPath = null
        Next       = "WorkflowEnd"
      }

      # ---------------------------------------------------------- NotifyComplete
      NotifyComplete = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          "FunctionName" = module.notify_lambda.function_arn
          Payload = {
            event_type             = "COMPLETE"
            "remediation_result.$" = "$.remediation_result.Payload"
          }
        }
        ResultPath = null
        Next       = "WorkflowEnd"
      }

      # --------------------------------------------------------------- End state
      WorkflowEnd = {
        Type = "Succeed"
      }
    }
  }

  # --------------------------------------------------------------------------
  # Legacy smoke-path definition (kept for reference; not deployed in Phase 4)
  # --------------------------------------------------------------------------
  smoke_state_machine = {
    Comment = "CloudSweep Phase 1 smoke path"
    StartAt = "InvokeSmokeHandler"
    States = {
      InvokeSmokeHandler = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = module.smoke_lambda.function_name
          Payload = {
            source = "eventbridge-scheduler"
            mode   = "smoke-test"
          }
        }
        End = true
      }
    }
  }
}
