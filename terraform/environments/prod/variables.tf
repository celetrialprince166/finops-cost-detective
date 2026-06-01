variable "aws_region" {
  description = "AWS region for the prod environment."
  type        = string
  default     = "us-east-1"
}

variable "lambda_source_path" {
  description = "Path to the shared Python Lambda source."
  type        = string
  default     = "../../../src/python"
}

variable "project_name" {
  description = "Project name prefix."
  type        = string
  default     = "cloudsweep-prod"
}

variable "schedule_expression" {
  description = "Smoke path schedule expression."
  type        = string
  default     = "rate(1 day)"
}
