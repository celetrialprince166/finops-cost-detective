# ==============================================================================
# Module: lab-seed
# ==============================================================================
# Cost Detective Audit — opt-in "zombie asset" generator for the sandbox.
#
# Creates three deliberately wasteful resources for use as demo evidence and
# for CloudSweep scanner / EBS garbage-collector validation:
#
#   1. Unattached gp3 EBS volume
#   2. Unassociated VPC Elastic IP
#   3. Idle EC2 instance (running, no workload)
#
# All resources are tagged CostCenter=<var.cost_center> (default "Lab") so the
# garbage collector and tagging-governance modules can safely filter on them.
#
# NOT for production. Always pair with the teardown documented in
# docs/lab/WALKTHROUGH.md § 9.
# ==============================================================================

locals {
  base_tags = merge(
    {
      CostCenter = var.cost_center
      Owner      = var.owner
      Project    = "cost-detective"
      ManagedBy  = "terraform"
      LabRole    = "zombie-asset"
    },
    var.extra_tags
  )
}

# ------------------------------------------------------------------------------
# Amazon Linux 2023 AMI (latest, region-aware)
# ------------------------------------------------------------------------------
data "aws_ssm_parameter" "al2023" {
  count = var.idle_instance_ami_id == "" ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  resolved_ami_id = var.idle_instance_ami_id != "" ? var.idle_instance_ami_id : data.aws_ssm_parameter.al2023[0].value
}

# ------------------------------------------------------------------------------
# Subnet resolution
# ------------------------------------------------------------------------------
# Priority:
#   1. var.subnet_id (explicit)               — use as-is.
#   2. var.create_subnet=true                 — create a /28 lab subnet in the
#                                               resolved VPC (vpc_id or default).
#   3. otherwise                              — look up the first existing
#                                               subnet in the resolved VPC at
#                                               var.ebs_availability_zone.
# Accounts without a default VPC must set var.vpc_id (and optionally
# var.create_subnet=true if the VPC has no subnets in the chosen AZ).
# ------------------------------------------------------------------------------

data "aws_vpc" "default" {
  count   = var.subnet_id == "" && var.vpc_id == "" ? 1 : 0
  default = true
}

locals {
  vpc_lookup_id = var.subnet_id != "" ? null : (
    var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
  )
}

data "aws_subnets" "existing" {
  count = var.subnet_id == "" && !var.create_subnet ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [local.vpc_lookup_id]
  }
  filter {
    name   = "availability-zone"
    values = [var.ebs_availability_zone]
  }
}

resource "aws_subnet" "lab" {
  count                   = var.subnet_id == "" && var.create_subnet ? 1 : 0
  vpc_id                  = local.vpc_lookup_id
  cidr_block              = var.subnet_cidr
  availability_zone       = var.ebs_availability_zone
  map_public_ip_on_launch = false

  tags = merge(local.base_tags, {
    Name = "${var.name_prefix}-subnet"
  })
}

locals {
  resolved_subnet_id = (
    var.subnet_id != "" ? var.subnet_id :
    var.create_subnet ? aws_subnet.lab[0].id :
    data.aws_subnets.existing[0].ids[0]
  )
}

# ------------------------------------------------------------------------------
# Security group — egress only, no ingress (idle instance does no work)
# ------------------------------------------------------------------------------
data "aws_subnet" "selected" {
  id = local.resolved_subnet_id
}

resource "aws_security_group" "idle" {
  name        = "${var.name_prefix}-idle-sg"
  description = "Lab idle EC2 - egress only, no ingress."
  vpc_id      = data.aws_subnet.selected.vpc_id

  egress {
    description = "Allow all outbound for instance bootstrap."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, { Name = "${var.name_prefix}-idle-sg" })
}

# ------------------------------------------------------------------------------
# 1. Unattached EBS Volume (zombie)
# ------------------------------------------------------------------------------
resource "aws_ebs_volume" "zombie" {
  availability_zone = var.ebs_availability_zone
  size              = var.ebs_size_gb
  type              = "gp3"
  encrypted         = true

  tags = merge(local.base_tags, {
    Name       = "${var.name_prefix}-zombie-volume"
    ZombieType = "unattached-ebs"
  })
}

# ------------------------------------------------------------------------------
# 2. Unassociated Elastic IP (orphan)
# ------------------------------------------------------------------------------
resource "aws_eip" "orphan" {
  domain = "vpc"

  tags = merge(local.base_tags, {
    Name       = "${var.name_prefix}-orphan-eip"
    ZombieType = "unassociated-eip"
  })
}

# ------------------------------------------------------------------------------
# 3. Idle EC2 Instance
# ------------------------------------------------------------------------------
# Runs Amazon Linux 2023 and does nothing — pure waste demonstration.
# CloudWatch CPUUtilization will sit near 0%; Trusted Advisor / Cost Explorer
# will surface it as underutilized after enough billing data accumulates.
resource "aws_instance" "idle" {
  ami                         = local.resolved_ami_id
  instance_type               = var.idle_instance_type
  subnet_id                   = local.resolved_subnet_id
  vpc_security_group_ids      = [aws_security_group.idle.id]
  associate_public_ip_address = false
  monitoring                  = false

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size           = 8
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
    tags = merge(local.base_tags, {
      Name = "${var.name_prefix}-idle-root"
    })
  }

  tags = merge(local.base_tags, {
    Name       = "${var.name_prefix}-idle-instance"
    ZombieType = "idle-ec2"
  })
}
