variable "table_name" {
  description = "State table name."
  type        = string
}

variable "ttl_attribute_name" {
  description = "TTL attribute name."
  type        = string
  default     = "ttl"
}

variable "kms_key_arn" {
  description = "KMS key ARN for DynamoDB server-side encryption. If not provided, uses AWS-managed key."
  type        = string
  default     = null
}
