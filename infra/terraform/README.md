# Terraform: artifact storage baseline

This module provisions a private S3 bucket, its KMS key, and separate least-privilege IAM task roles for the future API and worker. It does not deploy the API, create public endpoints, attach roles to compute, or wire the bucket into application code.

## Controls

- S3 Block Public Access and bucket-owner-enforced object ownership.
- SSE-KMS with automatic key rotation.
- TLS-only bucket policy.
- Versioning plus lifecycle expiry for current objects and short expiry for non-current versions.
- Incomplete multipart upload cleanup.
- Separate ECS task trust roles with source-account/source-ARN conditions.
- API object access limited to `api/*`; worker access limited to reading `worker-input/*` and writing `worker-results/*`.
- KMS operations restricted to this key, S3 via-service, and this bucket encryption context.
- Environment-specific role names via `environment_name`.
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

ECS/Fargate services, ALB, private subnets, SQS, Step Functions approval callbacks, Secrets Manager, CloudWatch alarms, GitHub OIDC deployment roles, and application-level artifact access remain future modules. The task roles are intentionally unattached until the matching services and prefix conventions are implemented. The current API keeps screenshots in memory and does not write to this bucket. Do not apply this module until the account, IAM policies, budget, region, and data lifecycle have been reviewed.
