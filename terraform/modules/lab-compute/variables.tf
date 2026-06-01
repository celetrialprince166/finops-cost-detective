variable "name_prefix" {
  description = "Prefix for the launch template, ASG, and security group."
  type        = string
}

variable "cost_center" {
  description = "Value of the CostCenter tag applied to every ASG-launched resource. Must satisfy the tag-governance deny policy."
  type        = string
  default     = "Lab"
}

variable "owner" {
  description = "Email or identifier for the Owner tag."
  type        = string
}

variable "ami_id" {
  description = "Override the Amazon Linux 2023 AMI lookup with an explicit AMI ID. Leave empty to use the SSM-published latest AL2023 AMI."
  type        = string
  default     = ""
}

variable "instance_types" {
  description = "List of instance types eligible for Spot diversification. The first entry is also the launch-template default for On-Demand baseline. Order does not matter for Spot capacity allocation when spot_allocation_strategy=price-capacity-optimized."
  type        = list(string)
  default     = ["t3.micro", "t3a.micro", "t2.micro", "t3.small"]
}

variable "vpc_id" {
  description = "VPC for the ASG and security group. Empty = use the default VPC."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Subnet IDs across AZs for the ASG. Empty = auto-discover all subnets in vpc_id (or default VPC)."
  type        = list(string)
  default     = []
}

variable "on_demand_base_capacity" {
  description = "Number of On-Demand instances kept at all times before Spot scale-out kicks in. Default 1 protects baseline availability."
  type        = number
  default     = 1
}

variable "on_demand_percentage_above_base" {
  description = "Percentage of capacity ABOVE the on_demand_base_capacity that should be On-Demand. 0 = all scale-out is Spot."
  type        = number
  default     = 0
}

variable "spot_allocation_strategy" {
  description = "How EC2 picks Spot pools. price-capacity-optimized balances cost and interruption risk; lowest-price purely minimises cost."
  type        = string
  default     = "price-capacity-optimized"
}

variable "min_size" {
  description = "ASG minimum capacity."
  type        = number
  default     = 1
}

variable "max_size" {
  description = "ASG maximum capacity. Default 4 supports the 'scale up to demonstrate Spot' walkthrough step."
  type        = number
  default     = 4
}

variable "desired_capacity" {
  description = "Initial desired capacity. Default 2 = 1 On-Demand + 1 Spot at baseline."
  type        = number
  default     = 2
}

variable "extra_tags" {
  description = "Additional tags merged onto module resources."
  type        = map(string)
  default     = {}
}
