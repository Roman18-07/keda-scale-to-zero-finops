resource "aws_cloudwatch_log_group" "lambda" {
  provider          = aws.target
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 1

  tags = {
    Name        = "/aws/lambda/${local.name}"
    Environment = var.environment
    Application = var.application
    ManagedBy   = "terraform"
  }
}
