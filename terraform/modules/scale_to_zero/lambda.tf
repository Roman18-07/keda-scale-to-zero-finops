resource "aws_lambda_function" "lambda" {
  provider      = aws.target
  function_name = local.name
  runtime       = "python3.13"
  handler       = "lambda_function.lambda_handler"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Zip"

  filename         = archive_file.lambda_dist_zip.output_path
  source_code_hash = archive_file.lambda_dist_zip.output_base64sha256

  publish = true

  environment {
    variables = {
      SSM_SLACK_TOKEN         = var.ssm_slack_token_name
      SKIP_SLACK_SIG          = "true"
      SLACK_SIGNING_SECRET    = var.slack_signing_secret
      SESSION_LABEL           = var.session_label
      SLASH_COMMAND           = var.slash_command
      DDB_TABLE_NAME          = aws_dynamodb_table.keda_scale_table.name
      DDB_GSI_DUE             = "gsi_due"
      DDB_GSI_EXPIRE          = "gsi_expire"
      SESSION_TTL_SEC         = tostring(var.session_ttl_sec)
      PING_GRACE_SEC          = tostring(var.ping_grace_sec)
      GRAFANA_SILENCE_ENABLED = tostring(var.grafana_silence_enabled)
      GRAFANA_API_URL         = var.grafana_api_url
      SSM_GRAFANA_TOKEN       = var.ssm_grafana_token_name
      CHANNEL_LOG_ID          = var.slack_log_channel_id
    }
  }

  depends_on = [
    archive_file.lambda_dist_zip,
    aws_cloudwatch_log_group.lambda
  ]
}


