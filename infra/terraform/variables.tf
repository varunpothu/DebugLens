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


variable "monthly_budget_usd" {
  description = "Monthly AWS cost alert threshold in USD. This is an alert budget, not a spending cap."
  type        = string
  default     = "33"
  validation {
    condition     = can(regex("^[0-9]+(\\.[0-9]{1,2})?$", var.monthly_budget_usd)) && can(tonumber(var.monthly_budget_usd) >= 1)
    error_message = "Monthly budget must be a positive USD amount."
  }
}

variable "budget_alert_email" {
  description = "Email for AWS Budget alerts. Leave blank only for a plan-only run; configure before applying."
  type        = string
  default     = ""
  validation {
    condition     = var.budget_alert_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.budget_alert_email))
    error_message = "Budget alert email must be a valid email address or empty."
  }
}

variable "enable_application_host" {
  description = "Create the cost-controlled single EC2 application host. Requires a DNS name and manually provisioned SSM secrets."
  type        = bool
  default     = false
}

variable "application_domain" {
  description = "Fully qualified DNS name for the private team app, e.g. debuglens.example.com. Point its A record at the instance public IP."
  type        = string
  default     = ""
  validation {
    condition     = var.application_domain == "" || can(regex("^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", var.application_domain))
    error_message = "Application domain must be a lowercase DNS name without a scheme or path."
  }
}

variable "ec2_instance_type" {
  description = "Budget-oriented Graviton instance type. Use an ARM64-compatible Docker image."
  type        = string
  default     = "t4g.small"
  validation {
    condition     = contains(["t4g.small", "t4g.medium"], var.ec2_instance_type)
    error_message = "Choose t4g.small or t4g.medium to keep the deployment intentionally small."
  }
}

variable "allowed_ingress_cidrs" {
  description = "Optional CIDR allow-list for HTTPS. Port 80 remains public for ACME certificate issuance and HTTPS redirects."
  type        = list(string)
  default     = []
}

variable "instance_root_volume_gb" {
  description = "Encrypted root volume size in GiB."
  type        = number
  default     = 20
  validation {
    condition     = var.instance_root_volume_gb >= 12 && var.instance_root_volume_gb <= 40
    error_message = "Root volume must be between 12 and 40 GiB."
  }
}


variable "analysis_provider" {
  description = "Vision provider to use in the deployed app. Mock is the safe default."
  type        = string
  default     = "mock"
  validation {
    condition     = contains(["mock", "openai_compatible", "anthropic", "gemini"], var.analysis_provider)
    error_message = "analysis_provider must be mock, openai_compatible, anthropic, or gemini."
  }
}

variable "vision_model" {
  description = "Model identifier for the OpenAI-compatible provider."
  type        = string
  default     = "gpt-4o-mini"
}

variable "vision_base_url" {
  description = "Base URL for the OpenAI-compatible provider."
  type        = string
  default     = "https://api.openai.com/v1"
}

variable "anthropic_model" {
  description = "Model identifier for Anthropic vision."
  type        = string
  default     = "claude-3-5-sonnet-latest"
}

variable "gemini_model" {
  description = "Model identifier for Gemini vision."
  type        = string
  default     = "gemini-2.5-flash"
}
