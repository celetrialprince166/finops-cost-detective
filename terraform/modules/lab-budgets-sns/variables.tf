variable "name_prefix" {
  description = "Prefix for the budget name and SNS topic name."
  type        = string
}

variable "budget_limit_usd" {
  description = "Monthly budget limit in USD. Default 50 matches the Cost Detective lab brief."
  type        = number
  default     = 50
}

variable "forecasted_threshold_percent" {
  description = "Percent of budget at which a FORECASTED notification fires. 100 = alert when forecast >= budget."
  type        = number
  default     = 100
}

variable "actual_threshold_percent" {
  description = "Percent of budget at which an ACTUAL spend notification fires. Set to 0 to disable the actual-spend notification."
  type        = number
  default     = 80
}

variable "subscriber_email" {
  description = "Email address to subscribe to the SNS topic. Must be confirmed via the AWS confirmation email before any alert is received."
  type        = string
}

variable "cost_filters" {
  description = "Optional cost filters applied to the budget. Example: { TagKeyValue = [\"user:CostCenter$Lab\"] }. Leave empty to budget across the whole account."
  type        = map(list(string))
  default     = {}
}

variable "tags" {
  description = "Tags applied to all resources created by this module."
  type        = map(string)
  default     = {}
}
