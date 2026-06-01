output "schedule_arn" {
  description = "Scheduler ARN."
  value       = aws_scheduler_schedule.this.arn
}
