module "scale_to_zero" {
  count = var.enable_scale_to_zero ? 1 : 0

  source = "./modules/scale_to_zero"

  providers = {
    aws.target = aws.target
  }

  environment                                          = var.environment
  application                                          = var.application
  slack_signing_secret                                 = var.slack_signing_secret
  ssm_slack_token_arn                                  = var.ssm_slack_token_arn
  ssm_slack_token_name                                 = var.ssm_slack_token_name
  slack_log_channel_id                                 = var.slack_log_channel_id
  user_inactive_work_session_check_schedule_expression = var.user_inactive_work_session_check_schedule_expression
  session_ttl_sec                                      = 3600
  ping_grace_sec                                       = 300
  session_label                                        = "staging"
  slash_command                                        = "/staging"
  grafana_silence_enabled                              = var.grafana_silence_enabled
  grafana_api_url                                      = var.grafana_api_url
  ssm_grafana_token_name                               = var.ssm_grafana_token_name
  ssm_grafana_token_arn                                = var.ssm_grafana_token_arn
}

