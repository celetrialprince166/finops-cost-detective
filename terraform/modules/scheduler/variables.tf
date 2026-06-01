variable "input" {
  description = "Input payload sent to the target."
  type        = string
  default     = "{}"
}

variable "name" {
  description = "Scheduler name."
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression."
  type        = string
}

variable "state_machine_arn" {
  description = "State machine to invoke."
  type        = string
}
