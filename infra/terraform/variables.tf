variable "aws_region" {
  description = "AWS region for DebugLens artifact storage."
  type        = string
  default     = "eu-west-2"
}

variable "artifact_bucket_name" {
  description = "Globally unique S3 bucket name. Do not use a public or personal-data-identifying name."
  type        = string
  validation {
    condition     = length(var.artifact_bucket_name) >= 3 && length(var.artifact_bucket_name) <= 63
    error_message = "S3 bucket name must be between 3 and 63 characters."
  }
}

variable "artifact_retention_days" {
  description = "Automatic expiry for current screenshot artifacts."
  type        = number
  default     = 7
  validation {
    condition     = var.artifact_retention_days >= 1 && var.artifact_retention_days <= 90
    error_message = "Artifact retention must be between 1 and 90 days."
  }
}

variable "tags" {
  description = "Default resource tags."
  type        = map(string)
  default = {
    Project     = "DebugLens"
    Environment = "development"
    ManagedBy   = "Terraform"
  }
}


variable "environment_name" {
  description = "Short environment label used to keep IAM role names distinct across environments."
  type        = string
  default     = "development"
  validation {
    condition     = can(regex("^[a-z0-9-]{1,20}$", var.environment_name))
    error_message = "Environment name must be 1–20 lowercase letters, digits, or hyphens."
  }
}
