# ==============================================================================
# Module Variables: approval-api
# ==============================================================================

variable "name" {
  description = "Base name used for the REST API and all child resources."
  type        = string
}

variable "approval_lambda_arn" {
  description = "ARN of the Lambda function that handles Slack approval callbacks."
  type        = string
}

variable "approval_lambda_name" {
  description = "Name of the approval Lambda function (used for the permission resource)."
  type        = string
}

variable "tags" {
  description = "Map of tags to apply to taggable resources in this module."
  type        = map(string)
  default     = {}
}
