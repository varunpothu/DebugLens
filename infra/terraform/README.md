# Terraform: cost-controlled AWS deployment

This Terraform root module includes a private encrypted S3 artifact bucket, a Cognito user pool for administrator-invited team accounts, budget notifications, a restricted EC2 pilot host, and its network/instance role. The host is **disabled by default**. See ../../deploy/README.md for the step-by-step Windows deployment runbook.

## Architecture and controls

- Region defaults to London (eu-west-2).
- S3 Block Public Access, bucket-owner-enforced ownership, SSE-KMS with key rotation, TLS-only bucket policy, versioning and short lifecycle expiry.
- Separate least-privilege IAM roles for future isolated workers and API artifact operations.
- Cognito hosted login with administrator-created accounts only, password policy and required authenticator-app MFA.
- OAuth2 Proxy protects the Streamlit UI; Caddy obtains and renews HTTPS certificates. The API has no host-published port and remains on the Docker network.
- EC2 uses Amazon Linux 2023 Graviton, encrypted gp3 root storage, IMDSv2 required, no inbound SSH, SSM Session Manager access, CPU credits in standard mode, and a small instance-size allow-list.
- Runtime secrets are read from SSM Parameter Store at boot. The API token and OAuth cookie secret must be created as SecureString parameters before enabling the host.
- AWS Budget alerts at 50%, 80%, and 100% actual spend and at 100% forecasted spend when budget_alert_email is set. **Budgets are alerts, not hard spending caps.**
- CloudWatch bootstrap log retention is 14 days. No NAT Gateway, load balancer, RDS, or multi-AZ resources are provisioned by this pilot.

## Remote state is required before apply

The Cognito client secret is stored in SSM SecureString and also appears in Terraform state. Before applying, create a private, versioned, encrypted S3 state bucket, restrict its access to the deployment role, and enable a bucket policy that denies non-TLS requests. Then initialise the configured S3 backend with:

~~~powershell
terraform init -backend-config="bucket=YOUR_STATE_BUCKET" -backend-config="key=debuglens/production/terraform.tfstate" -backend-config="region=eu-west-2" -backend-config="encrypt=true" -backend-config="use_lockfile=true"
~~~

Terraform 1.10 or later is required for native S3 lockfiles. Never commit state files, backend credentials, .tfvars files, API tokens, OAuth cookie secrets, or provider keys.

## Validate without deploying

CI validates formatting and configuration without contacting your AWS account:

~~~powershell
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
~~~

The CI workflow runs Terraform 1.10 and initialises without a backend. For a local plan, supply a unique artifact_bucket_name and review all resources and costs.

## Safe rollout

1. Set a real budget alert email and create the state bucket. The email is also used for backup-failure SNS alerts; confirm the SNS subscription after applying.
2. Apply with enable_application_host=false to create the budget, artifact bucket, and Cognito identity configuration without an EC2 host.
3. Create the API token and OAuth cookie secret directly in SSM as SecureString values; never paste them into chat or source control.
4. Set application_domain to a domain you control and enable the host only after secrets exist.
5. Review the plan before applying, add an A record to the returned public IP, and verify HTTPS and Cognito sign-in.
6. Test account invitation, MFA, unauthorized access, backup/export, and recovery before storing valuable data.

## Cost expectations and limitations

The default alert is USD 33/month, an approximate £25 target rather than a guaranteed bill. Actual charges vary by region, exchange rates, tax, public IPv4, storage, transfer, logs, and provider API usage. No AWS service in this module can guarantee a hard cost ceiling. Monitor the first week closely.

This is a single-instance pilot with local SQLite storage. Daily encrypted S3 backups are configured for the optional host and retained according to database_backup_retention_days, with SNS email alerts on failures when the configured subscription is confirmed. Backups will not run until you apply the host resources. Verify the first successful upload and perform a restore drill before relying on them. The pilot is not highly available and still lacks per-user application RBAC, per-user audit attribution, automated deployment via GitHub OIDC, distributed rate limits, backup-failure alerting, and an independent production security review. Do not use it for regulated or highly sensitive screenshots until those controls are complete.
