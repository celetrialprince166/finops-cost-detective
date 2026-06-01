output "table_name" {
  description = "State table name."
  value       = aws_dynamodb_table.this.name
}

output "table_arn" {
  description = "State table ARN."
  value       = aws_dynamodb_table.this.arn
}
