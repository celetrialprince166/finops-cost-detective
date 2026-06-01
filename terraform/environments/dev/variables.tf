variable "aws_region" {
  description = "AWS region for the dev environment."
  type        = string
  default     = "eu-west-1"
}

variable "lambda_source_path" {
  description = "Path to the src/ directory. Zipped as-is so python/ is a package inside the ZIP, preserving relative imports."
  type        = string
  default     = "../../../src"
}

variable "project_name" {
  description = "Project name prefix."
  type        = string
  default     = "cloudsweep-dev"
}

variable "schedule_expression" {
  description = "Smoke path schedule expression."
  type        = string
  default     = "rate(1 day)"
}

# ------------------------------------------------------------------------------
# LAB — Cost Detective Audit (opt-in)
# ------------------------------------------------------------------------------
# These variables gate the lab-seed module and downstream lab modules. They
# default off so a normal `terraform apply` deploys only the CloudSweep stack.
# Flip `enable_lab_seed=true` to deploy the zombie-asset sandbox.
# ------------------------------------------------------------------------------

variable "enable_lab_seed" {
  description = "LAB. When true, deploys the lab-seed module (unattached EBS, unassociated EIP, idle EC2) for the Cost Detective audit walkthrough."
  type        = bool
  default     = false
}

variable "lab_cost_center" {
  description = "LAB. Value used for the CostCenter tag on every lab resource. Also the filter used by the EBS garbage collector and tagging-governance demo."
  type        = string
  default     = "Lab"
}

variable "lab_owner_email" {
  description = "LAB. Email recorded in the Owner tag on every lab resource. Required when enable_lab_seed=true."
  type        = string
  default     = ""
}

variable "lab_idle_instance_type" {
  description = "LAB. EC2 instance type for the idle zombie instance. Override to t3.micro for free-tier-friendly demos."
  type        = string
  default     = "t3.large"
}

variable "lab_availability_zone" {
  description = "LAB. AZ for the EBS volume and idle EC2. Must be a valid AZ in aws_region."
  type        = string
  default     = "eu-west-1a"
}

variable "lab_vpc_id" {
  description = "LAB. Optional VPC ID for lab resources. If empty and no default VPC exists, set lab_subnet_id instead."
  type        = string
  default     = ""
}

variable "lab_subnet_id" {
  description = "LAB. Optional subnet ID for the idle EC2. If empty, the module picks a subnet from lab_vpc_id or the default VPC."
  type        = string
  default     = ""
}

# --- lab-budgets-sns ---------------------------------------------------------

variable "enable_lab_budget" {
  description = "LAB. When true, deploys the lab-budgets-sns module (AWS Budget + SNS topic + email subscription)."
  type        = bool
  default     = false
}

variable "lab_budget_email" {
  description = "LAB. Email address subscribed to the cost-alerts SNS topic. Required when enable_lab_budget=true."
  type        = string
  default     = ""
}

variable "lab_budget_limit_usd" {
  description = "LAB. Monthly USD budget cap. Default matches the Cost Detective brief."
  type        = number
  default     = 50
}

variable "lab_budget_actual_threshold_percent" {
  description = "LAB. Percent of budget that triggers an ACTUAL spend alert. Set to 0 to disable."
  type        = number
  default     = 80
}

# --- lab-tag-governance ------------------------------------------------------

variable "enable_lab_tag_governance" {
  description = "LAB. When true, deploys the lab-tag-governance module (IAM deny policy + test role; Config rule optional)."
  type        = bool
  default     = false
}

variable "lab_required_tag_key" {
  description = "LAB. Tag key required on EC2 RunInstances calls by the deny policy."
  type        = string
  default     = "CostCenter"
}

variable "lab_enable_config_rule" {
  description = "LAB. When true (and enable_lab_tag_governance=true), also create the AWS Config required-tags rule."
  type        = bool
  default     = false
}

variable "lab_create_config_recorder" {
  description = "LAB. When true, the tag-governance module also creates the Config recorder + S3 bucket. Set false if Config is already active in the account."
  type        = bool
  default     = false
}

# --- lab-compute -------------------------------------------------------------

variable "enable_lab_compute" {
  description = "LAB. When true, deploys the lab-compute module (Mixed Instances Spot Auto Scaling Group)."
  type        = bool
  default     = false
}

variable "lab_compute_instance_types" {
  description = "LAB. Instance types for Spot diversification in the lab ASG."
  type        = list(string)
  default     = ["t3.micro", "t3a.micro", "t2.micro", "t3.small"]
}

variable "lab_compute_on_demand_base" {
  description = "LAB. On-Demand base capacity for the lab ASG."
  type        = number
  default     = 1
}

variable "lab_compute_desired_capacity" {
  description = "LAB. Initial desired capacity for the lab ASG."
  type        = number
  default     = 2
}

variable "lab_compute_max_size" {
  description = "LAB. Max size for the lab ASG (enables the scale-up demo step)."
  type        = number
  default     = 4
}
