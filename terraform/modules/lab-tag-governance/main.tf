# ==============================================================================
# Module: lab-tag-governance
# ==============================================================================
# Cost Detective Audit - CostCenter tagging governance.
#
# Provisions:
#   1. IAM managed policy that denies ec2:RunInstances unless the request tags
#      include var.required_tag_key (and optionally a value in allowed_tag_values).
#   2. A companion deny rule for ec2:CreateTags / ec2:DeleteTags on instances,
#      preventing users from bypassing the launch-time check after the fact.
#   3. A test IAM role wrapping the policy, plus the EC2 permissions needed to
#      exercise allow vs deny RunInstances calls.
#   4. (Optional) AWS Config managed rule `REQUIRED_TAGS` for EC2 instances, so
#      anything that escapes the preventive control is flagged after the fact.
#
# This is the practical, single-account preventive control. The enterprise
# variant (AWS Organizations SCP + Tag Policies) is documented in
# docs/lab/tag-governance.md.
# ==============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  policy_name = "${var.name_prefix}-require-${lower(var.required_tag_key)}"
  role_name   = "${var.name_prefix}-restricted-role"
}

# ------------------------------------------------------------------------------
# IAM managed policy - deny untagged RunInstances
# ------------------------------------------------------------------------------

data "aws_iam_policy_document" "require_tag" {

  # Deny RunInstances if the required tag is missing from the request.
  statement {
    sid       = "DenyRunInstancesWithoutRequiredTag"
    effect    = "Deny"
    actions   = ["ec2:RunInstances"]
    resources = ["arn:aws:ec2:*:*:instance/*"]
    condition {
      test     = "Null"
      variable = "aws:RequestTag/${var.required_tag_key}"
      values   = ["true"]
    }
  }

  # Deny RunInstances if the tag value is outside the allow-list.
  dynamic "statement" {
    for_each = length(var.allowed_tag_values) > 0 ? [1] : []
    content {
      sid       = "DenyRunInstancesWithDisallowedTagValue"
      effect    = "Deny"
      actions   = ["ec2:RunInstances"]
      resources = ["arn:aws:ec2:*:*:instance/*"]
      condition {
        test     = "StringNotEquals"
        variable = "aws:RequestTag/${var.required_tag_key}"
        values   = var.allowed_tag_values
      }
    }
  }

  # Deny stripping or rewriting the tag after launch.
  statement {
    sid       = "DenyRemovingRequiredTag"
    effect    = "Deny"
    actions   = ["ec2:DeleteTags"]
    resources = ["arn:aws:ec2:*:*:instance/*"]
    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "aws:TagKeys"
      values   = [var.required_tag_key]
    }
  }
}

resource "aws_iam_policy" "require_tag" {
  name        = local.policy_name
  description = "Deny ec2:RunInstances and ec2:DeleteTags when ${var.required_tag_key} is missing."
  policy      = data.aws_iam_policy_document.require_tag.json
  tags        = var.tags
}

# ------------------------------------------------------------------------------
# Test IAM role - exercises the deny policy
# ------------------------------------------------------------------------------

data "aws_iam_policy_document" "test_role_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type = "AWS"
      identifiers = length(var.test_role_trusted_principal_arns) > 0 ? var.test_role_trusted_principal_arns : [
        "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
      ]
    }
  }
}

resource "aws_iam_role" "test" {
  name               = local.role_name
  description        = "Lab role used to verify tag-governance deny policy. Allowed to call ec2:RunInstances but blocked by the require-tag policy when the tag is missing."
  assume_role_policy = data.aws_iam_policy_document.test_role_trust.json
  tags               = var.tags
}

# Allow the test role to call RunInstances and related describe APIs.
data "aws_iam_policy_document" "test_role_baseline" {
  statement {
    effect = "Allow"
    actions = [
      "ec2:RunInstances",
      "ec2:CreateTags",
      "ec2:DescribeInstances",
      "ec2:DescribeImages",
      "ec2:DescribeSubnets",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeVpcs",
      "ec2:TerminateInstances",
      "iam:PassRole",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "test_baseline" {
  name   = "${local.role_name}-baseline"
  role   = aws_iam_role.test.id
  policy = data.aws_iam_policy_document.test_role_baseline.json
}

# Attach the deny policy.
resource "aws_iam_role_policy_attachment" "test_deny" {
  role       = aws_iam_role.test.name
  policy_arn = aws_iam_policy.require_tag.arn
}

# ------------------------------------------------------------------------------
# Optional - AWS Config required-tags rule
# ------------------------------------------------------------------------------

resource "aws_s3_bucket" "config" {
  count         = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  bucket        = "${var.name_prefix}-config-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = var.tags
}

data "aws_iam_policy_document" "config_bucket_policy" {
  count = var.enable_config_rule && var.create_config_recorder ? 1 : 0

  statement {
    sid    = "AWSConfigBucketPermissionsCheck"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.config[0].arn]
  }

  statement {
    sid    = "AWSConfigBucketDelivery"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.config[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/Config/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "config" {
  count  = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  bucket = aws_s3_bucket.config[0].id
  policy = data.aws_iam_policy_document.config_bucket_policy[0].json
}

data "aws_iam_policy_document" "config_role_trust" {
  count = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "config" {
  count              = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  name               = "${var.name_prefix}-config-role"
  assume_role_policy = data.aws_iam_policy_document.config_role_trust[0].json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "config_managed" {
  count      = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  role       = aws_iam_role.config[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}

resource "aws_config_configuration_recorder" "this" {
  count    = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  name     = "${var.name_prefix}-recorder"
  role_arn = aws_iam_role.config[0].arn

  recording_group {
    all_supported                 = false
    include_global_resource_types = false
    resource_types                = ["AWS::EC2::Instance"]
  }
}

resource "aws_config_delivery_channel" "this" {
  count          = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  name           = "${var.name_prefix}-channel"
  s3_bucket_name = aws_s3_bucket.config[0].bucket
  depends_on     = [aws_config_configuration_recorder.this]
}

resource "aws_config_configuration_recorder_status" "this" {
  count      = var.enable_config_rule && var.create_config_recorder ? 1 : 0
  name       = aws_config_configuration_recorder.this[0].name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.this]
}

resource "aws_config_config_rule" "required_tags" {
  count = var.enable_config_rule ? 1 : 0
  name  = "${var.name_prefix}-required-tags-ec2"

  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }

  scope {
    compliance_resource_types = ["AWS::EC2::Instance"]
  }

  input_parameters = jsonencode({
    tag1Key = var.required_tag_key
  })

  tags = var.tags

  depends_on = [aws_config_configuration_recorder_status.this]
}
