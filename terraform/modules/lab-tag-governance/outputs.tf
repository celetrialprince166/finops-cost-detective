output "policy_arn" {
  description = "ARN of the managed deny policy. Attach to any IAM principal that should be constrained."
  value       = aws_iam_policy.require_tag.arn
}

output "policy_name" {
  description = "Name of the managed deny policy."
  value       = aws_iam_policy.require_tag.name
}

output "test_role_arn" {
  description = "ARN of the test IAM role used to exercise allow vs deny RunInstances calls."
  value       = aws_iam_role.test.arn
}

output "test_role_name" {
  description = "Name of the test IAM role."
  value       = aws_iam_role.test.name
}

output "config_rule_name" {
  description = "Name of the AWS Config rule, or null when enable_config_rule=false."
  value       = try(aws_config_config_rule.required_tags[0].name, null)
}

output "assume_role_cli_hint" {
  description = "PowerShell snippet to assume the test role for verification commands."
  value       = "aws sts assume-role --role-arn ${aws_iam_role.test.arn} --role-session-name lab-tag-test"
}
