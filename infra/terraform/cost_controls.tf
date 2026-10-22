resource "aws_budgets_budget" "monthly_cost" {
  name         = "debuglens-monthly-${var.environment_name}"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.budget_alert_email == "" ? [] : [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      notification_type          = "ACTUAL"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }

  dynamic "notification" {
    for_each = var.budget_alert_email == "" ? [] : [100]
    content {
      comparison_operator        = "GREATER_THAN"
      notification_type          = "FORECASTED"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }

  tags = {
    Component = "cost-control"
  }
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/debuglens/${var.environment_name}/application"
  retention_in_days = 14
  tags              = { Component = "application-logs" }
}
