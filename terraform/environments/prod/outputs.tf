output "schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule."
  value       = module.scheduler.schedule_arn
}

output "smoke_lambda_arn" {
  description = "ARN of the smoke-test Lambda function."
  value       = module.smoke_lambda.function_arn
}

output "state_machine_arn" {
  description = "ARN of the smoke-test Step Functions state machine."
  value       = module.smoke_state_machine.state_machine_arn
}

output "state_table_name" {
  description = "Name of the DynamoDB table used to store scanner state."
  value       = module.state_tracker.table_name
}
