# Cloud bootstrap (no local Terraform)

This bootstrap is designed for the DebugLens cloud-only workflow. Use a browser to create a CloudFormation stack; no Terraform or AWS CLI installation is required on your laptop.

## What it creates

- A private S3 Terraform state bucket with Block Public Access, bucket-owner-enforced ownership, versioning, SSE-S3 encryption, and a TLS-only bucket policy. The bucket is retained if the stack is deleted.
- A GitHub OIDC provider if one does not already exist (or accepts the existing provider ARN).
- A GitHub Actions role restricted to this repository's named GitHub Environment. The role has AWS read-only inspection permissions plus write access only to the Terraform state and lockfile paths in the state bucket.

The role is for **plan-only** use. It does not have permissions to create or modify the application infrastructure. Do not attach AdministratorAccess to this role. This template does not create the DebugLens application host.

## 1. Create the GitHub Environment first

In GitHub, open the repository Settings → Environments → New environment and name it `aws-plan`. Configure deployment branches to allow only `main`. The AWS trust policy requires a GitHub OIDC subject matching:

`repo:varunpothu/DebugLens:environment:aws-plan`

Do not add AWS keys as GitHub secrets.

## 2. Create the CloudFormation stack in AWS Console

1. Sign in to the AWS Management Console using your browser, with MFA enabled.
2. Switch to **Europe (London), eu-west-2**.
3. Open CloudFormation → Create stack → With new resources (standard).
4. For the template, use the reviewed file `infra/bootstrap/cloudformation-github-oidc.yml` from the merged `main` branch. Download the file from GitHub to your computer if the console asks you to upload a template file.
5. Stack name: `debuglens-cloud-bootstrap`.
6. Keep `GitHubRepository=varunpothu/DebugLens` and `GitHubEnvironment=aws-plan`.
7. If IAM already has an OIDC provider with URL `https://token.actions.githubusercontent.com`, set `ExistingGitHubOIDCProviderArn` to its ARN. Otherwise leave it blank so the stack creates one.
8. Review the template and changes. Acknowledge IAM resource creation when prompted, then create the stack.
9. Wait for `CREATE_COMPLETE`. If it fails, inspect the CloudFormation Events tab and stop; do not repeatedly retry without addressing the cause.

This stack creates a role and a state bucket, not the application server. Review the template and your account's IAM policies before creating it. The deploying identity must have permission to create these resources.

## 3. Configure GitHub repository variables

In GitHub Settings → Secrets and variables → Actions → Variables, add:

- `AWS_ROLE_ARN`: the `GitHubTerraformPlanRoleArn` stack output.
- `TF_STATE_BUCKET`: the `TerraformStateBucketName` stack output.
- `BUDGET_ALERT_EMAIL`: an email address you control for cost alerts.

These are identifiers/configuration, not AWS access keys. Do not put credentials in variables.

## 4. Run the plan workflow

After the cloud-only Terraform workflow PR has been reviewed and merged to `main`:

1. Open Actions → **AWS Terraform Plan (host disabled)** → Run workflow.
2. Select `main` and start the run.
3. Confirm the OIDC role assumption succeeds.
4. Review the Terraform plan artifact/log. The workflow is intended to set `enable_application_host=false` and does not run `terraform apply`.

The plan role is read-only for AWS infrastructure. A later, separately reviewed apply workflow should use a different role and a protected GitHub Environment with required reviewers. Never reuse this plan role for apply.

## Security and cost notes

- GitHub OIDC provides short-lived AWS credentials; no long-lived access key is stored in GitHub.
- The state bucket is private and versioned because Terraform state can contain sensitive values.
- The stack does not set an AWS spending cap. AWS Budget notifications are alerts only.
- Do not deploy the public host until you own a domain, runtime secrets are set in SSM SecureString, and the plan has been reviewed.
- This bootstrap is a starting point, not a claim of 100% security. Have an AWS administrator review the template and permissions for your account before use.
