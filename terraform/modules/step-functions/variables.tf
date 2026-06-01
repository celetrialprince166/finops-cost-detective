variable "definition" {
  description = "Amazon States Language definition."
  type        = string
}

variable "lambda_function_arns" {
  description = "Lambda ARNs the state machine may invoke."
  type        = list(string)
  default     = []
}

variable "name" {
  description = "State machine name."
  type        = string
}
