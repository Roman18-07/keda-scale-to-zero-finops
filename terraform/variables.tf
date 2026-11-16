variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "target_account_deploy_role" {
  description = "Optional IAM role ARN to assume in the target account. Leave empty to use the current credentials"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Environment, e.g. staging, prod"
  type        = string
}

variable "application" {
  description = "Application name. Must match the Kubernetes namespace where KEDA is installed (used in the IRSA trust policy)"
  type        = string
  default     = "keda"
}

variable "eks_cluster_name" {
  description = "Name of the EKS cluster where KEDA runs"
  type        = string
}

variable "extra_tags" {
  description = "Additional default tags applied to all AWS resources"
  type        = map(string)
  default     = {}
}

variable "slack_log_channel_id" {
  description = "Slack channel ID where start/stop/extend actions are logged"
  type        = string
  default     = ""
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

variable "enable_scale_to_zero" {
  description = "Enable scale to zero"
  type        = bool
}

variable "user_inactive_work_session_check_schedule_expression" {
  type = string
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
  description = "SSM parameter ARN for Grafana Service Account token"
  type        = string
  default     = ""
}
