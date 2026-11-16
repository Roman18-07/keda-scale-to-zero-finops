resource "aws_cloudwatch_event_rule" "lambda_schedule" {
  provider            = aws.target
  name                = "${local.name}-user-inactive-work-session-check"
  schedule_expression = var.user_inactive_work_session_check_schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  provider  = aws.target
  rule      = aws_cloudwatch_event_rule.lambda_schedule.name
  arn       = aws_lambda_function.lambda.arn
  target_id = "lambda"
}

resource "aws_lambda_permission" "allow_eventbridge" {
  provider      = aws.target
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.lambda_schedule.arn
}

