output "invoke_url" {
  value = "${aws_apigatewayv2_api.http_api.api_endpoint}/${var.environment}"
}

output "ddb_table_name" {
  value = aws_dynamodb_table.keda_scale_table.name
}

output "ddb_table_arn" {
  value = aws_dynamodb_table.keda_scale_table.arn
}

