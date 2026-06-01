# ==============================================================================
# Terraform Module: State Tracker (DynamoDB Table)
# ==============================================================================
# This module creates a DynamoDB table for tracking cloud resource scan state.
# Used to maintain idempotency and prevent duplicate processing during scans.
#
# Table Schema:
# - Primary Key: resource_id (partition key) + scan_date (sort key)
# - GSI: resource_type + scan_date for efficient queries by resource type
# - TTL: Auto-expires records based on configured TTL attribute
# ==============================================================================

resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "resource_id"
  range_key    = "scan_date"

  # Primary key attributes
  attribute {
    name = "resource_id"
    type = "S"
  }

  attribute {
    name = "scan_date"
    type = "S"
  }

  attribute {
    name = "resource_type"
    type = "S"
  }

  # Global Secondary Index for querying by resource type and date
  # Enables efficient scans for specific resource types within date ranges
  global_secondary_index {
    name            = "type-date-index"
    hash_key        = "resource_type"
    range_key       = "scan_date"
    projection_type = "ALL"
  }

  # TTL configuration for automatic data expiration
  # Reduces storage costs by removing old scan records
  ttl {
    attribute_name = var.ttl_attribute_name
    enabled        = true
  }

  # Server-side encryption for data at rest protection
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }
}