output "artifact_bucket_name" {
  description = "Private S3 bucket for approved DebugLens artifacts."
  value       = aws_s3_bucket.artifacts.bucket
}

output "artifact_bucket_arn" {
  description = "S3 bucket ARN."
  value       = aws_s3_bucket.artifacts.arn
}

output "artifact_kms_key_arn" {
  description = "KMS key ARN used for server-side encryption."
  value       = aws_kms_key.artifacts.arn
}


output "api_task_role_arn" {
  description = "Least-privilege ECS task role for API artifact access; not attached to a service by this module."
  value       = aws_iam_role.api.arn
}

output "worker_task_role_arn" {
  description = "Separate least-privilege ECS task role for worker artifact access; not attached to a service by this module."
  value       = aws_iam_role.worker.arn
}


output "monthly_budget_usd" {
  description = "Monthly AWS cost alert threshold in USD. AWS Budgets alerts do not cap spending."
  value       = aws_budgets_budget.monthly_cost.limit_amount
}

output "cognito_user_pool_id" {
  description = "Invite-only Cognito user pool for team sign-in."
  value       = aws_cognito_user_pool.team.id
}

output "cognito_client_id" {
  description = "Public OAuth client ID used by oauth2-proxy with PKCE."
  value       = aws_cognito_user_pool_client.team.id
}

output "cognito_hosted_domain" {
  description = "AWS Cognito hosted login domain."
  value       = "https://${aws_cognito_user_pool_domain.team.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "application_url" {
  description = "HTTPS URL for the private team application when the host is enabled."
  value       = var.enable_application_host && var.application_domain != "" ? "https://${var.application_domain}" : null
}

output "application_public_ip" {
  description = "Public IPv4 address for the HTTPS host; create a DNS A record for application_domain."
  value       = try(aws_instance.app[0].public_ip, null)
}


output "database_backup_retention_days" {
  description = "Retention period for encrypted SQLite backups stored under the private backups/ prefix."
  value       = var.database_backup_retention_days
}
