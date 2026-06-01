provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      ManagedBy = "Terraform"
      Project   = "CloudSweep"
      # Environment will be derived from project_name
    }
  }
}
