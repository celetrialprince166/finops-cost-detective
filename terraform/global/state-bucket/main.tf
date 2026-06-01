# ==============================================================================
# Terraform Configuration for AWS Global State Backend
# ==============================================================================
# This module provisions S3 and DynamoDB resources required for storing
# Terraform remote state and managing state locking.
#
# Resources created:
# - S3 bucket: Stores Terraform state files with versioning and encryption
# - DynamoDB table: Provides state locking to prevent concurrent modifications
#
# NOTE: Provider is passed via the `providers` argument in the calling module.
# ==============================================================================

# ------------------------------------------------------------------------------
# S3 Bucket for Terraform State Storage
# ------------------------------------------------------------------------------
# Stores Terraform state files with:
# - Versioning enabled for state history
# - Server-side encryption (AES256)
# - Public access blocked for security
# ------------------------------------------------------------------------------

resource "aws_s3_bucket" "tf_state" {
  bucket = "${var.project_name}-tf-state"
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ------------------------------------------------------------------------------
# DynamoDB Table for State Locking
# ------------------------------------------------------------------------------
# Prevents concurrent Terraform operations from corrupting state.
# Uses pay-per-request billing for cost efficiency.
# ------------------------------------------------------------------------------

resource "aws_dynamodb_table" "tf_lock" {
  name         = "${var.project_name}-tf-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}