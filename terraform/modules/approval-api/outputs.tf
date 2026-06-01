output "api_endpoint" {
  description = "Full invoke URL for the Slack callback — set this in your Slack app's Interactivity & Shortcuts settings."
  value       = "${aws_api_gateway_stage.this.invoke_url}/approval/callback"
}

output "rest_api_id" {
  description = "ID of the API Gateway REST API."
  value       = aws_api_gateway_rest_api.this.id
}

output "stage_name" {
  description = "Deployed API Gateway stage name."
  value       = aws_api_gateway_stage.this.stage_name
}
