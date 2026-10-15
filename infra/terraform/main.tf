terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = var.tags
  }
}

resource "aws_kms_key" "artifacts" {
  description             = "DebugLens screenshot artifact encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags                    = { Component = "artifact-encryption" }
}

resource "aws_kms_alias" "artifacts" {
  name          = "alias/debuglens-artifacts"
  target_key_id = aws_kms_key.artifacts.key_id
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = var.artifact_bucket_name
  force_destroy = false
  tags          = { Component = "private-artifact-storage" }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.artifacts.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    id     = "expire-debug-artifacts"
    status = "Enabled"
    filter { prefix = "" }
    expiration { days = var.artifact_retention_days }
    noncurrent_version_expiration { noncurrent_days = 7 }
    abort_incomplete_multipart_upload { days_after_initiation = 2 }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  bucket = aws_s3_bucket.artifacts.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.artifacts.arn,
        "${aws_s3_bucket.artifacts.arn}/*"
      ]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.artifacts]
}


# Separate task roles for the future API and isolated worker. These roles are not
# attached to compute resources by this storage-only module; see infra/terraform/README.md.
data "aws_caller_identity" "current" {}

locals {
  ecs_task_assume_role = {
    Version   = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
        }
      }
    }]
  }

  s3_kms_conditions = {
    StringEquals = {
      "kms:ViaService"                   = "s3.${var.aws_region}.amazonaws.com"
      "kms:EncryptionContext:aws:s3:arn" = aws_s3_bucket.artifacts.arn
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "debuglens-api-${var.environment_name}-artifacts"
  assume_role_policy = jsonencode(local.ecs_task_assume_role)
  description        = "Least-privilege task role for DebugLens API artifact operations."
  tags               = { Component = "api-task-role" }
}

resource "aws_iam_role_policy" "api_artifacts" {
  name   = "debuglens-api-artifacts"
  role   = aws_iam_role.api.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [
      {
        Sid      = "ApiArtifactObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.artifacts.arn}/api/*"]
      },
      {
        Sid       = "ApiArtifactEncryption"
        Effect    = "Allow"
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
        Resource  = [aws_kms_key.artifacts.arn]
        Condition = local.s3_kms_conditions
      }
    ]
  })
}

resource "aws_iam_role" "worker" {
  name               = "debuglens-worker-${var.environment_name}-artifacts"
  assume_role_policy = jsonencode(local.ecs_task_assume_role)
  description        = "Least-privilege task role for DebugLens isolated worker artifact operations."
  tags               = { Component = "worker-task-role" }
}

resource "aws_iam_role_policy" "worker_artifacts" {
  name   = "debuglens-worker-artifacts"
  role   = aws_iam_role.worker.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [
      {
        Sid      = "WorkerReadInputs"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.artifacts.arn}/worker-input/*"]
      },
      {
        Sid      = "WorkerWriteResults"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.artifacts.arn}/worker-results/*"]
      },
      {
        Sid       = "WorkerArtifactEncryption"
        Effect    = "Allow"
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
        Resource  = [aws_kms_key.artifacts.arn]
        Condition = local.s3_kms_conditions
      }
    ]
  })
}
