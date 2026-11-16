variable "environment" {
  description = "Environment, e.g. staging, prod"
  type        = string
}

variable "application" {
  description = "Application name"
  type        = string
}

variable "slack_signing_secret" {
  type      = string
  default   = ""
  sensitive = true
}

variable "ssm_slack_token_arn" {
  type = string
}

variable "ssm_slack_token_name" {
  type = string
}

variable "slack_log_channel_id" {
  description = "Slack channel ID where start/stop/extend actions are logged"
  type        = string
  default     = ""
}

variable "user_inactive_work_session_check_schedule_expression" {
  type = string
}

variable "session_ttl_sec" {
  description = "Session TTL in seconds (for DynamoDB TTL)"
  type        = number
  default     = 3600
}

variable "ping_grace_sec" {
  description = "Slack confirmation wait window (seconds)"
  type        = number
  default     = 300
}

variable "session_label" {
  description = "Human-readable label used in Slack messages (e.g. 'staging', 'JupyterHub')"
  type        = string
  default     = "staging"
}

variable "slash_command" {
  description = "Slash command name used in help text (e.g. '/staging', '/jhub')"
  type        = string
  default     = "/staging"
}

variable "grafana_silence_enabled" {
  description = "Enable automatic Grafana silence on scale-to-zero"
  type        = bool
  default     = false
}

variable "grafana_api_url" {
  description = "Grafana base URL for silence API calls"
  type        = string
  default     = ""
}

variable "ssm_grafana_token_name" {
  description = "SSM parameter name for Grafana Service Account token"
  type        = string
  default     = ""
}

variable "ssm_grafana_token_arn" {
  description = "SSM parameter ARN for Grafana Service Account token (for IAM)"
  type        = string
  default     = ""
}
