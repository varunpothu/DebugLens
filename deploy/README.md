# AWS deployment: private team pilot

This is a deliberately small, single-instance deployment target for a trusted team. It uses EC2 Graviton, Docker Compose, Caddy-managed HTTPS, Cognito sign-in, SSM Parameter Store, and CloudWatch. It avoids an Application Load Balancer, NAT Gateway, RDS, and multi-AZ infrastructure to protect the initial budget.

## Important boundaries

- No resources are created until you run Terraform. The enable_application_host setting defaults to false.
- The AWS Budget is an alert, not a hard spending cap. AWS can continue charging after the threshold is reached. Review the AWS Billing console and set a card/billing alert as well.
- The default budget is USD 33/month, an approximate alert equivalent to £25. Exchange rates, tax, AI-provider usage, network egress, and usage outside this stack can change the final bill.
- Cognito allows administrator-created accounts only. Self-service sign-up is disabled. Authenticator-app MFA is required.
- All authenticated team members currently have the same application permissions. Per-user role-based authorization and per-user audit attribution still need a separate application change before sensitive or regulated team use.
- The API and UI have no host-published ports. Caddy is the only public container entry point. SSH is not opened; use Systems Manager Session Manager.
- The API defaults to mock analysis. External vision-provider access and browser capture remain disabled unless deliberately configured.
- The app uses a local SQLite database on the EC2 root volume. A daily encrypted S3 backup timer is configured for the optional host, with a separate `backups/` prefix and configurable 7–90 day retention. The schedule is inactive until the host is applied; verify the first successful upload and complete a restore drill before storing valuable records. This remains a single-instance pilot, not high availability.
- Terraform state includes sensitive Cognito client metadata. Use the encrypted, versioned S3 backend described below before applying.

## 1. Prerequisites

On Windows, install AWS CLI v2 and Terraform 1.10 or later. Sign in using an IAM Identity Center profile or another approved short-lived IAM role. Do not create long-lived IAM access keys for this project and never put credentials in GitHub or this repository.

Check identity and region:

~~~powershell
aws sts get-caller-identity
aws configure get region
~~~

Use eu-west-2 (London). The IAM identity needs permission to create the resources in this Terraform module, manage the state bucket, and use Systems Manager. Use an administrator-approved role rather than broadening permissions casually.

## 2. Create the Terraform state bucket first

The S3 backend bucket is a one-time bootstrap resource and is intentionally not created by the same Terraform state it stores. In PowerShell:

~~~powershell
$AccountId = (aws sts get-caller-identity --query Account --output text).Trim()
$StateBucket = "debuglens-tfstate-$AccountId"
aws s3api create-bucket --bucket $StateBucket --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2
aws s3api put-public-access-block --bucket $StateBucket --region eu-west-2 --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-ownership-controls --bucket $StateBucket --region eu-west-2 --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
aws s3api put-bucket-versioning --bucket $StateBucket --region eu-west-2 --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket $StateBucket --region eu-west-2 --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
~~~

Apply a TLS-only bucket policy before using this state bucket for team/production work. In PowerShell:

~~~powershell
$Policy = @{
  Version = "2012-10-17"
  Statement = @(@{
    Sid = "DenyInsecureTransport"
    Effect = "Deny"
    Principal = "*"
    Action = "s3:*"
    Resource = @("arn:aws:s3:::$StateBucket", "arn:aws:s3:::$StateBucket/*")
    Condition = @{ Bool = @{ "aws:SecureTransport" = "false" } }
  })
} | ConvertTo-Json -Depth 10
$Policy | Set-Content -Path .\state-bucket-policy.json
aws s3api put-bucket-policy --bucket $StateBucket --region eu-west-2 --policy file://state-bucket-policy.json
Remove-Item .\state-bucket-policy.json
~~~

Restrict bucket access to the deployment IAM role before using this state bucket for team/production work. Do not make the state bucket public. The state may contain sensitive infrastructure values.

Initialise the backend:

~~~powershell
Set-Location infra/terraform
terraform init -backend-config="bucket=$StateBucket" -backend-config="key=debuglens/production/terraform.tfstate" -backend-config="region=eu-west-2" -backend-config="encrypt=true" -backend-config="use_lockfile=true"
~~~

Keep this state bucket when destroying application resources. Do not run terraform destroy against the state bucket.

## 3. Configure cost alerts and create identity/storage

Choose a bucket name that is globally unique. Set your actual billing-alert email; do not paste AWS credentials into the terminal transcript or chat.

~~~powershell
$ArtifactBucket = "debuglens-artifacts-$AccountId"
terraform plan -var="aws_region=eu-west-2" -var="environment_name=production" -var="artifact_bucket_name=$ArtifactBucket" -var="budget_alert_email=YOUR_EMAIL_ADDRESS" -var="monthly_budget_usd=33" -var="enable_application_host=false"
~~~

Review the plan. Only then apply:

~~~powershell
terraform apply -var="aws_region=eu-west-2" -var="environment_name=production" -var="artifact_bucket_name=$ArtifactBucket" -var="budget_alert_email=YOUR_EMAIL_ADDRESS" -var="monthly_budget_usd=33" -var="enable_application_host=false"
~~~

This stage creates the budget, private encrypted artifact bucket, Cognito user pool/client, and runtime configuration parameters. It does not create an EC2 host. Confirm the budget is visible in AWS Billing and Cost Management.

## 4. Add runtime secrets to SSM

Create a long random API bearer token and a separate 32-byte base64 OAuth cookie secret. The values below are generated locally and sent directly to AWS Systems Manager Parameter Store as SecureString; they are not printed by the commands or sent to ChatGPT.

~~~powershell
$ApiToken = python -c "import secrets; print(secrets.token_hex(32))"
$CookieSecret = python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
aws ssm put-parameter --region eu-west-2 --name /debuglens/production/api-access-token --type SecureString --value $ApiToken --overwrite
aws ssm put-parameter --region eu-west-2 --name /debuglens/production/oauth-cookie-secret --type SecureString --value $CookieSecret --overwrite
Remove-Variable ApiToken, CookieSecret
~~~

Do not echo, commit, or paste either value. Terraform stores the Cognito client secret as an SSM SecureString; the EC2 role can read only parameters under /debuglens/production/*.

## 5. Choose a DNS name before launching the host

You need a domain name you control, for example debuglens.yourdomain.com. The domain must point to the EC2 public IP for Caddy to obtain a trusted TLS certificate. Do not use a domain you do not control. Launch the host only after this deployment branch has been merged to main, because the bootstrap script clones main.

Set application_domain and enable the host only after the SSM secrets exist:

~~~powershell
terraform plan -var="aws_region=eu-west-2" -var="environment_name=production" -var="artifact_bucket_name=$ArtifactBucket" -var="budget_alert_email=YOUR_EMAIL_ADDRESS" -var="monthly_budget_usd=33" -var="application_domain=debuglens.yourdomain.com" -var="enable_application_host=true"
~~~

Review every resource and estimated cost before applying. Then apply with the same variables. Terraform outputs application_public_ip. Create an A record for debuglens.yourdomain.com pointing to that IP. Allow DNS to propagate; Caddy obtains and renews HTTPS certificates automatically on ports 80/443.

If the domain is not ready, leave enable_application_host=false. Do not expose the app over plain HTTP.

## 6. Invite team members

Open the Cognito user pool in the London region. Use Create user to invite each approved teammate by their work email. Keep self-registration disabled. Require MFA for the team according to your organisation's policy. Remove accounts when people leave the team.

The app is protected by Cognito-backed OAuth2 Proxy. The API is internal to the Docker network and has a separate bearer token. This provides separate sign-in accounts, but it does not yet provide per-user roles inside DebugLens.

## 7. Verify and operate

The default provider is mock and external screenshot transfer is disabled. To enable a real vision provider, first review the provider's data-processing terms and obtain team approval. Store the API key as a SecureString in Systems Manager Parameter Store, using one of these names:

- OpenAI-compatible provider: /debuglens/production/vision-api-key
- Anthropic: /debuglens/production/anthropic-api-key
- Gemini: /debuglens/production/gemini-api-key

Then re-run Terraform with the intended provider and model, for example:

~~~powershell
terraform apply -var="aws_region=eu-west-2" -var="environment_name=production" -var="artifact_bucket_name=$ArtifactBucket" -var="budget_alert_email=YOUR_EMAIL_ADDRESS" -var="monthly_budget_usd=33" -var="application_domain=debuglens.yourdomain.com" -var="enable_application_host=true" -var="analysis_provider=openai_compatible" -var="vision_model=gpt-4o-mini" -var="allow_unredacted_screenshots=true"
~~~

This opt-in is global for the deployment, not a per-screenshot consent prompt. Enabling it means screenshots may be sent to the configured external provider. Keep it false unless the team has approved that transfer. After updating SSM secrets or configuration, use Systems Manager Session Manager to run sudo systemctl restart debuglens so the containers reload their environment. For Anthropic or Gemini, set analysis_provider to the matching name and configure that provider's model variable.

- Check https://YOUR_DOMAIN/ and confirm unauthenticated visitors are redirected to Cognito sign-in.
- Confirm an invited account can sign in and an uninvited account cannot create an account.
- Confirm HTTP redirects to HTTPS and the browser certificate is trusted.
- From Systems Manager Session Manager, inspect systemctl status debuglens, docker compose ps, and journalctl -u debuglens.
- Bootstrap logs are sent to /debuglens/production/application with 14-day retention. The CPU alarm is a signal to investigate, not an autoscaler.
- The deployment currently builds images on the EC2 host from the public GitHub main branch. For controlled releases, review the commit and update the checkout deliberately; a GitHub OIDC-based CI/CD deployment is a follow-up hardening step.
- Test an export/backup and recovery before real team data is stored.

## Cost and safety checklist

- [ ] Budget alert email is configured and alerts are visible.
- [ ] State bucket is private, versioned, encrypted, and access-restricted.
- [ ] terraform plan reviewed before every apply.
- [ ] DNS domain is controlled by the team and HTTPS works.
- [ ] SSM secrets exist before the host is enabled.
- [ ] No inbound SSH rule exists.
- [ ] Cognito self-sign-up is disabled and team accounts are invited individually.
- [ ] Mock mode remains the default until provider data handling and spend are approved.
- [ ] Backups and recovery are tested.
- [ ] Cost is reviewed daily during the first week. Budget notifications do not stop charges.

## Known limitations before production use

This is a low-cost pilot, not a highly available or fully production-hardened service. There is one EC2 instance and one local SQLite database; there is no automatic failover, managed database, distributed rate limiter, per-user application RBAC, full tenant isolation, or automated deployment pipeline yet. Complete those controls and an independent security review before handling sensitive or regulated screenshots.


## Scheduled SQLite backups

When the optional host is enabled, a systemd timer creates a consistent SQLite snapshot daily around 02:15 UTC, verifies its integrity and SHA-256 digest, and uploads the database plus a metadata sidecar to the private S3 `backups/` prefix using the artifact KMS key. The default retention is 30 days and can be changed with `database_backup_retention_days` (7–90 days). The instance role can read/write only that backup prefix; it cannot list the bucket.

After applying the infrastructure, verify the first successful run in `/var/log/debuglens-backup.log` and the CloudWatch application log group. Perform the restore procedure in [the operations runbook](../docs/operations.md#aws-pilot-restore-a-scheduled-s3-backup) before storing valuable records. The timer is configuration only until the host is deployed; CI cannot verify real AWS credentials, permissions, S3 uploads, or recovery.
