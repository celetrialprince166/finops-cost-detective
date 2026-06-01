# ==============================================================================
# Module: lab-compute
# ==============================================================================
# Cost Detective Audit - "cost-aware" stateless workload demonstration.
#
# Provisions:
#   1. Launch template using Amazon Linux 2023, IMDSv2 required, egress-only SG,
#      encrypted root volume, and CostCenter=<var.cost_center> tags applied to
#      every launched instance and volume.
#   2. Auto Scaling Group with a mixed_instances_policy:
#        - On-Demand base capacity (default 1) for stability.
#        - 100% Spot for scale-out beyond the base.
#        - 4 instance-type overrides for Spot capacity diversification.
#        - price-capacity-optimized allocation strategy.
#   3. Multi-AZ deployment across whichever subnets are passed (or discovered).
#
# The launched instances do nothing useful - they exist to demonstrate the
# mixed On-Demand + Spot capacity model and how Spot scale-out reduces cost
# for stateless workloads. Always pair with the budgets-sns module and run
# teardown after the walkthrough.
# ==============================================================================

locals {
  base_tags = merge(
    {
      CostCenter = var.cost_center
      Owner      = var.owner
      Project    = "cost-detective"
      ManagedBy  = "terraform"
      LabRole    = "spot-asg"
    },
    var.extra_tags
  )
}

# ------------------------------------------------------------------------------
# AMI resolution
# ------------------------------------------------------------------------------

data "aws_ssm_parameter" "al2023" {
  count = var.ami_id == "" ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  resolved_ami_id = var.ami_id != "" ? var.ami_id : data.aws_ssm_parameter.al2023[0].value
}

# ------------------------------------------------------------------------------
# VPC + subnet resolution
# ------------------------------------------------------------------------------

data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

locals {
  resolved_vpc_id = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
}

data "aws_subnets" "available" {
  count = length(var.subnet_ids) == 0 ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [local.resolved_vpc_id]
  }
}

locals {
  resolved_subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.available[0].ids
}

# ------------------------------------------------------------------------------
# Security group - egress only
# ------------------------------------------------------------------------------

resource "aws_security_group" "asg" {
  name        = "${var.name_prefix}-asg-sg"
  description = "Lab Spot ASG instances - egress only, no ingress."
  vpc_id      = local.resolved_vpc_id

  egress {
    description = "Allow all outbound for instance bootstrap."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, { Name = "${var.name_prefix}-asg-sg" })
}

# ------------------------------------------------------------------------------
# Launch template
# ------------------------------------------------------------------------------

resource "aws_launch_template" "this" {
  name_prefix   = "${var.name_prefix}-lt-"
  image_id      = local.resolved_ami_id
  instance_type = var.instance_types[0]

  vpc_security_group_ids = [aws_security_group.asg.id]

  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 8
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.base_tags, { Name = "${var.name_prefix}-asg-instance" })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = merge(local.base_tags, { Name = "${var.name_prefix}-asg-volume" })
  }

  tags = merge(local.base_tags, { Name = "${var.name_prefix}-launch-template" })

  lifecycle {
    create_before_destroy = true
  }
}

# ------------------------------------------------------------------------------
# Auto Scaling Group with mixed instances policy
# ------------------------------------------------------------------------------

resource "aws_autoscaling_group" "this" {
  name                = "${var.name_prefix}-asg"
  vpc_zone_identifier = local.resolved_subnet_ids
  min_size            = var.min_size
  max_size            = var.max_size
  desired_capacity    = var.desired_capacity
  health_check_type   = "EC2"
  capacity_rebalance  = true

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = var.on_demand_base_capacity
      on_demand_percentage_above_base_capacity = var.on_demand_percentage_above_base
      spot_allocation_strategy                 = var.spot_allocation_strategy
    }

    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.this.id
        version            = "$Latest"
      }

      dynamic "override" {
        for_each = var.instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }

  dynamic "tag" {
    for_each = local.base_tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.name_prefix}-asg"
    propagate_at_launch = false
  }

  lifecycle {
    create_before_destroy = true
  }
}
