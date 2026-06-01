# ==============================================================================
# Local Values: Production Environment
# ==============================================================================
# Defines inline values derived from other configuration inputs.
# Used to construct the Step Functions state machine definition.
# ==============================================================================

locals {
  # --------------------------------------------------------------------------
  # Smoke State Machine Definition (Amazon States Language)
  # --------------------------------------------------------------------------
  # This defines the workflow executed by Step Functions when triggered.
  # Currently configured as a single-step workflow:
  #
  # 1. InvokeSmokeHandler: Invokes the smoke Lambda function with event payload
  #    - Task type: Lambda invoke
  #    - Payload includes: source (event trigger) and mode (smoke-test)
  #    - End state: true (workflow terminates after Lambda execution)
  #
  # This is the Phase 1 smoke test path - a simple workflow that validates
  # the Lambda can be invoked and receives the scheduler event correctly.
  # Future phases will add more states (e.g., resource discovery, evaluation).
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