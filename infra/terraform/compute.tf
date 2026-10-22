data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ssm_parameter" "amazon_linux_2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

locals {
  app_https_ingress_cidrs = length(var.allowed_ingress_cidrs) > 0 ? var.allowed_ingress_cidrs : ["0.0.0.0/0"]
  instance_parameter_arn  = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/debuglens/${var.environment_name}/*"
}

resource "aws_vpc" "app" {
  count                = var.enable_application_host ? 1 : 0
  cidr_block           = "10.73.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "debuglens-${var.environment_name}", Component = "application-network" }
}

resource "aws_subnet" "public" {
  count                   = var.enable_application_host ? 1 : 0
  vpc_id                  = aws_vpc.app[0].id
  cidr_block              = "10.73.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "debuglens-${var.environment_name}-public", Component = "application-network" }
}

resource "aws_internet_gateway" "app" {
  count  = var.enable_application_host ? 1 : 0
  vpc_id = aws_vpc.app[0].id
  tags   = { Name = "debuglens-${var.environment_name}", Component = "application-network" }
}

resource "aws_route_table" "public" {
  count  = var.enable_application_host ? 1 : 0
  vpc_id = aws_vpc.app[0].id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.app[0].id
  }
  tags = { Name = "debuglens-${var.environment_name}-public", Component = "application-network" }
}

resource "aws_route_table_association" "public" {
  count          = var.enable_application_host ? 1 : 0
  subnet_id      = aws_subnet.public[0].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_security_group" "app" {
  count       = var.enable_application_host ? 1 : 0
  name        = "debuglens-${var.environment_name}-web"
  description = "Only public web ports; SSH is intentionally not exposed."
  vpc_id      = aws_vpc.app[0].id

  ingress {
    description = "Public HTTP for ACME certificate issuance and HTTPS redirect"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS protected by Cognito-backed OAuth2 Proxy"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = local.app_https_ingress_cidrs
  }

  ingress {
    description = "HTTP/3 over QUIC"
    from_port   = 443
    to_port     = 443
    protocol    = "udp"
    cidr_blocks = local.app_https_ingress_cidrs
  }

  egress {
    description = "Outbound HTTPS for updates, Cognito, SSM, and configured vision providers"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Component = "application-ingress" }
}

resource "aws_iam_role" "instance" {
  count       = var.enable_application_host ? 1 : 0
  name        = "debuglens-${var.environment_name}-instance"
  description = "SSM-only administration and restricted runtime parameter access."
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
  tags = { Component = "application-instance-role" }
}

resource "aws_iam_role_policy_attachment" "instance_ssm" {
  count      = var.enable_application_host ? 1 : 0
  role       = aws_iam_role.instance[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "instance_runtime" {
  count = var.enable_application_host ? 1 : 0
  name  = "debuglens-runtime-parameters-and-logs"
  role  = aws_iam_role.instance[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadDebugLensRuntimeParameters"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = [local.instance_parameter_arn]
      },
      {
        Sid      = "DecryptSSMParametersViaSSM"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = ["*"]
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com"
          }
          StringLike = {
            "kms:EncryptionContext:PARAMETER_ARN" = local.instance_parameter_arn
          }
        }
      },
      {
        Sid      = "WriteBootstrapLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = ["${aws_cloudwatch_log_group.application.arn}:*"]
      },
      {
        Sid      = "ReadAndWriteDatabaseBackups"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.artifacts.arn}/backups/*"]
      },
      {
        Sid      = "EncryptAndDecryptDatabaseBackups"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
        Resource = [aws_kms_key.artifacts.arn]
        Condition = local.s3_kms_conditions
      }
    ]
  })
}

resource "aws_iam_instance_profile" "app" {
  count = var.enable_application_host ? 1 : 0
  name  = "debuglens-${var.environment_name}-instance"
  role  = aws_iam_role.instance[0].name
}

resource "aws_instance" "app" {
  count                       = var.enable_application_host ? 1 : 0
  ami                         = data.aws_ssm_parameter.amazon_linux_2023_arm64.value
  instance_type               = var.ec2_instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.app[0].id]
  iam_instance_profile        = aws_iam_instance_profile.app[0].name
  associate_public_ip_address = true
  user_data = templatefile("${path.module}/bootstrap.sh.tftpl", {
    aws_region               = var.aws_region
    environment_name         = var.environment_name
    artifact_bucket_name     = aws_s3_bucket.artifacts.bucket
    artifact_kms_key_arn     = aws_kms_key.artifacts.arn
  })
  user_data_replace_on_change = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    encrypted             = true
    volume_type           = "gp3"
    volume_size           = var.instance_root_volume_gb
    delete_on_termination = true
  }

  credit_specification {
    cpu_credits = "standard"
  }

  lifecycle {
    precondition {
      condition     = var.application_domain != ""
      error_message = "Set application_domain to a DNS name you control before enabling the application host."
    }
    precondition {
      condition     = var.budget_alert_email != ""
      error_message = "Set budget_alert_email before enabling the public application host."
    }
  }

  tags = {
    Name      = "debuglens-${var.environment_name}"
    Component = "application-host"
  }

  depends_on = [
    aws_ssm_parameter.application_domain,
    aws_ssm_parameter.cognito_issuer,
    aws_ssm_parameter.cognito_client_id,
    aws_iam_role_policy_attachment.instance_ssm,
    aws_iam_role_policy.instance_runtime
  ]
}

resource "aws_cloudwatch_metric_alarm" "instance_cpu" {
  count               = var.enable_application_host ? 1 : 0
  alarm_name          = "debuglens-${var.environment_name}-high-cpu"
  alarm_description   = "CPU above 85% for 15 minutes. Investigate load and consider scaling."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 85
  treat_missing_data  = "notBreaching"
  dimensions          = { InstanceId = aws_instance.app[0].id }
  tags                = { Component = "cost-and-health-monitoring" }
}
