# Terraform: artifact storage baseline

This module provisions only a private S3 bucket and its KMS key. It does not deploy the API, create public endpoints, or wire the bucket into application code.

## Controls

- S3 Block Public Access and bucket-owner-enforced object ownership.
- SSE-KMS with automatic key rotation.
- TLS-only bucket policy.
- Versioning plus lifecycle expiry for current objects and short expiry for non-current versions.
- Incomplete multipart upload cleanup.
- Region defaults to London (eu-west-2); change only after data-residency review.

## Validate without deploying

~~~powershell
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -var="artifact_bucket_name=replace-with-a-globally-unique-name"
~~~

Do not run terraform apply until the AWS account, budget alerts, region, retention policy, IAM access, key recovery, and data-processing requirements are reviewed. Terraform state can contain sensitive infrastructure metadata; store it remotely with encryption, locking, restricted access, and versioning before team use. Never commit terraform.tfstate or credentials.

## Not yet implemented

ECS/Fargate, ALB, private subnets, SQS, Step Functions approval callbacks, Secrets Manager, CloudWatch alarms, GitHub OIDC deployment roles, and application-level artifact access are future modules. The current API keeps screenshots in memory and does not write to this bucket.
