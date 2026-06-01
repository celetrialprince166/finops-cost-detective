variable "name_prefix" {
  description = "Name prefix applied to all seeded resources. Used for Name tag."
  type        = string
}

variable "cost_center" {
  description = "Value for the CostCenter tag applied to every seeded resource. Used as the lab filter throughout the audit."
  type        = string
  default     = "Lab"
}

variable "owner" {
  description = "Email or identifier recorded in the Owner tag for accountability."
  type        = string
}

variable "ebs_size_gb" {
  description = "Size of the unattached zombie EBS volume in GiB. Keep small to control cost."
  type        = number
  default     = 8
}

variable "ebs_availability_zone" {
  description = "AZ for the zombie EBS volume. Must be a valid AZ in the deployment region."
  type        = string
  default     = "eu-west-1a"
}

variable "idle_instance_type" {
  description = "Instance type for the idle EC2. Large enough to demonstrate waste but bounded by the lab budget. Override to t3.micro for free-tier-friendly demos."
  type        = string
  default     = "t3.large"
}

variable "idle_instance_ami_id" {
  description = "Override the Amazon Linux 2023 AMI lookup with an explicit AMI ID. Leave empty to use the SSM-published latest AL2023 AMI."
  type        = string
  default     = ""
}

variable "vpc_id" {
  description = "VPC ID to pick a subnet from when subnet_id is not given. If both vpc_id and subnet_id are empty, the module falls back to the default VPC."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet ID for the idle EC2 instance. If empty, the module discovers an existing subnet in ebs_availability_zone (or creates one when create_subnet=true)."
  type        = string
  default     = ""
}

variable "create_subnet" {
  description = "When true and subnet_id is empty, create a dedicated /28 lab subnet inside the resolved VPC. Set this to true only when the target VPC has no existing subnets in ebs_availability_zone (e.g. an empty custom VPC). Default false suits default VPCs."
  type        = bool
  default     = false
}

variable "subnet_cidr" {
  description = "CIDR block used when create_subnet=true. Must fit inside the resolved VPC."
  type        = string
  default     = "172.31.250.0/28"
}

variable "extra_tags" {
  description = "Additional tags merged onto every seeded resource. CostCenter, Owner, Project, ManagedBy are always set by the module."
  type        = map(string)
  default     = {}
}
