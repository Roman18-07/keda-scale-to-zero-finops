output "keda_operator_role_arn" {
  description = "IAM role ARN for the keda-operator service account (eks.amazonaws.com/role-arn annotation)"
  value       = aws_iam_role.apps_keda.arn
}

output "scale_to_zero_invoke_url" {
  description = "Slack Request URL (slash command + interactivity) for the main environment"
  value       = var.enable_scale_to_zero ? module.scale_to_zero[0].invoke_url : null
}

output "scale_to_zero_ddb_table_name" {
  description = "DynamoDB table name to use in KEDA aws-dynamodb triggers"
  value       = var.enable_scale_to_zero ? module.scale_to_zero[0].ddb_table_name : null
}

output "scale_to_zero_jhub_invoke_url" {
  description = "Slack Request URL for the JupyterHub instance"
  value       = var.enable_scale_to_zero ? module.scale_to_zero_jhub[0].invoke_url : null
}

output "scale_to_zero_jhub_ddb_table_name" {
  description = "DynamoDB table name for the JupyterHub instance"
  value       = var.enable_scale_to_zero ? module.scale_to_zero_jhub[0].ddb_table_name : null
}
