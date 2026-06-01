output "launch_template_id" {
  description = "ID of the lab launch template."
  value       = aws_launch_template.this.id
}

output "launch_template_name" {
  description = "Name of the lab launch template."
  value       = aws_launch_template.this.name
}

output "asg_name" {
  description = "Name of the lab Auto Scaling Group."
  value       = aws_autoscaling_group.this.name
}

output "asg_arn" {
  description = "ARN of the lab Auto Scaling Group."
  value       = aws_autoscaling_group.this.arn
}

output "security_group_id" {
  description = "Security group ID applied to ASG instances."
  value       = aws_security_group.asg.id
}

output "instance_types" {
  description = "Instance types in the mixed-instances policy."
  value       = var.instance_types
}
