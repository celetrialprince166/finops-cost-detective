variable "name_prefix" {
  description = "Prefix for the managed policy and test role names."
  type        = string
}

variable "required_tag_key" {
  description = "The tag key that must be present on EC2 instance launches. Default 'CostCenter' matches the Cost Detective brief."
  type        = string
  default     = "CostCenter"
}

variable "allowed_tag_values" {
  description = "Optional list of allowed values for required_tag_key. Empty list means any non-empty value is accepted."
  type        = list(string)
  default     = []
}

variable "test_role_trusted_principal_arns" {
  description = "ARNs that may assume the test role (e.g. your IAM user ARN). Default '*' grants account-wide assume access; tighten this in real use."
  type        = list(string)
  default     = []
}

variable "enable_config_rule" {
  description = "When true, creates AWS Config required-tags rule for EC2 instances. Requires a Config recorder + delivery channel to be active (module can create those if create_config_recorder=true)."
  type        = bool
  default     = false
}

variable "create_config_recorder" {
  description = "When true and enable_config_rule=true, the module also creates the Config recorder, delivery channel, and S3 bucket. Set to false if a recorder already exists in the account."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to module-created IAM, S3, and Config resources where supported."
  type        = map(string)
  default     = {}
}
