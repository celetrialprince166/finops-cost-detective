output "schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule."
  value       = module.scheduler.schedule_arn
}

output "smoke_lambda_arn" {
  description = "ARN of the smoke-test Lambda function."
  value       = module.smoke_lambda.function_arn
}

output "scan_lambda_arn" {
  description = "ARN of the scan Lambda function."
  value       = module.scan_lambda.function_arn
}

output "evaluate_lambda_arn" {
  description = "ARN of the evaluate Lambda function."
  value       = module.evaluate_lambda.function_arn
}

output "remediate_lambda_arn" {
  description = "ARN of the remediate Lambda function."
  value       = module.remediate_lambda.function_arn
}

output "notify_lambda_arn" {
  description = "ARN of the notify Lambda function."
  value       = module.notify_lambda.function_arn
}

output "approval_lambda_arn" {
  description = "ARN of the approval Lambda function."
  value       = module.approval_lambda.function_arn
}

output "state_machine_arn" {
  description = "ARN of the full CloudSweep Step Functions state machine."
  value       = module.cloudsweep_state_machine.state_machine_arn
}

output "smoke_state_machine_arn" {
  description = "ARN of the Phase 1 smoke-test Step Functions state machine."
  value       = module.smoke_state_machine.state_machine_arn
}

output "state_table_name" {
  description = "Name of the DynamoDB table used to store scanner state."
  value       = module.state_tracker.table_name
}

output "approval_api_endpoint" {
  description = "Slack callback URL — configure this in your Slack app's Interactivity settings."
  value       = module.approval_api.api_endpoint
}

# ------------------------------------------------------------------------------
# LAB — Cost Detective Audit outputs (null when enable_lab_seed=false)
# ------------------------------------------------------------------------------

output "lab_seed_ebs_volume_id" {
  description = "LAB. Zombie EBS volume ID, or null when lab seed is disabled."
  value       = try(module.lab_seed[0].ebs_volume_id, null)
}

output "lab_seed_eip_allocation_id" {
  description = "LAB. Orphan EIP allocation ID, or null when lab seed is disabled."
  value       = try(module.lab_seed[0].eip_allocation_id, null)
}

output "lab_seed_eip_public_ip" {
  description = "LAB. Orphan EIP public IP, or null when lab seed is disabled."
  value       = try(module.lab_seed[0].eip_public_ip, null)
}

output "lab_seed_idle_instance_id" {
  description = "LAB. Idle EC2 instance ID, or null when lab seed is disabled."
  value       = try(module.lab_seed[0].idle_instance_id, null)
}

output "lab_seed_summary" {
  description = "LAB. Human-readable summary of seeded zombie resources."
  value       = try(module.lab_seed[0].summary, "lab-seed disabled")
}

# --- lab-budgets-sns ---------------------------------------------------------

output "lab_budget_sns_topic_arn" {
  description = "LAB. Cost-alerts SNS topic ARN, or null when lab budget is disabled."
  value       = try(module.lab_budget[0].sns_topic_arn, null)
}

output "lab_budget_name" {
  description = "LAB. AWS Budget name, or null when lab budget is disabled."
  value       = try(module.lab_budget[0].budget_name, null)
}

output "lab_budget_subscription_arn" {
  description = "LAB. Email subscription ARN (PendingConfirmation until the email link is clicked)."
  value       = try(module.lab_budget[0].subscription_arn, null)
}

# --- lab-tag-governance ------------------------------------------------------

output "lab_tag_policy_arn" {
  description = "LAB. ARN of the require-tag managed policy, or null when disabled."
  value       = try(module.lab_tag_governance[0].policy_arn, null)
}

output "lab_tag_test_role_arn" {
  description = "LAB. ARN of the test role used to exercise deny/allow RunInstances."
  value       = try(module.lab_tag_governance[0].test_role_arn, null)
}

output "lab_tag_assume_role_cmd" {
  description = "LAB. PowerShell-ready CLI command to assume the test role."
  value       = try(module.lab_tag_governance[0].assume_role_cli_hint, null)
}

# --- lab-compute -------------------------------------------------------------

output "lab_compute_asg_name" {
  description = "LAB. Mixed Instances Spot ASG name, or null when lab compute is disabled."
  value       = try(module.lab_compute[0].asg_name, null)
}

output "lab_compute_launch_template_id" {
  description = "LAB. Launch template ID, or null when lab compute is disabled."
  value       = try(module.lab_compute[0].launch_template_id, null)
}

output "lab_compute_instance_types" {
  description = "LAB. Instance types in the ASG's mixed-instances policy."
  value       = try(module.lab_compute[0].instance_types, null)
}
