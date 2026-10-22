resource "aws_cognito_user_pool" "team" {
  name                = "debuglens-${var.environment_name}-team"
  username_attributes = ["email"]
  auto_verified_attributes = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 3
    password_history_size            = 5
  }

  mfa_configuration = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  tags = {
    Component = "team-identity"
  }
}

resource "aws_cognito_user_pool_domain" "team" {
  domain       = "debuglens-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.team.id
}

resource "aws_cognito_user_pool_client" "team" {
  name         = "debuglens-private-web"
  user_pool_id = aws_cognito_user_pool.team.id

  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls = var.application_domain == "" ? [
    "http://localhost:4180/oauth2/callback"
    ] : [
    "https://${var.application_domain}/oauth2/callback"
  ]
  logout_urls = var.application_domain == "" ? [
    "http://localhost:4180/"
    ] : [
    "https://${var.application_domain}/"
  ]

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  access_token_validity         = 60
  id_token_validity             = 60
  refresh_token_validity        = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_ssm_parameter" "application_domain" {
  name        = "/debuglens/${var.environment_name}/application-domain"
  description = "Public DNS name used by the DebugLens reverse proxy."
  type        = "String"
  value       = var.application_domain
  overwrite   = true
}

resource "aws_ssm_parameter" "cognito_issuer" {
  name        = "/debuglens/${var.environment_name}/cognito-issuer"
  description = "OIDC issuer for the DebugLens team user pool."
  type        = "String"
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.team.id}"
  overwrite   = true
}

resource "aws_ssm_parameter" "cognito_client_id" {
  name        = "/debuglens/${var.environment_name}/cognito-client-id"
  description = "Public Cognito OAuth client ID for the private team web app."
  type        = "String"
  value       = aws_cognito_user_pool_client.team.id
  overwrite   = true
}

resource "aws_ssm_parameter" "cognito_client_secret" {
  name        = "/debuglens/${var.environment_name}/oauth-client-secret"
  description = "Confidential OAuth client secret used by the internal reverse proxy."
  type        = "SecureString"
  value       = aws_cognito_user_pool_client.team.client_secret
  overwrite   = true
}
