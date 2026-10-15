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
