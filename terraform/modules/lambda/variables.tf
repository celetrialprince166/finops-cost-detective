variable "create_dlq" {
  description = "Whether to create a DLQ for the function."
  type        = bool
  default     = true
}

variable "additional_policy_json" {
  description = "Optional JSON IAM policy document with extra statements attached as an inline policy on the Lambda role."
  type        = string
  default     = null
}

variable "layer_arns" {
  description = "List of Lambda layer ARNs to attach to the function (max 5)."
  type        = list(string)
  default     = []
}

variable "description" {
  description = "Lambda function description."
  type        = string
  default     = "CloudSweep Lambda function"
}

variable "environment_variables" {
  description = "Environment variables to inject into the function."
  type        = map(string)
  default     = {}
}

variable "function_name" {
  description = "Lambda function name."
  type        = string
}

variable "handler" {
  description = "Lambda handler."
  type        = string
}

variable "memory_size" {
  description = "Lambda memory size."
  type        = number
  default     = 256
}

variable "runtime" {
  description = "Lambda runtime."
  type        = string
  default     = "python3.12"
}

variable "source_path" {
  description = "Path to the Lambda source directory."
  type        = string
}

variable "timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 30
}
