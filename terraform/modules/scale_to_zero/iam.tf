resource "aws_iam_role" "lambda_role" {
  provider = aws.target
  name     = "${local.name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Effect = "Allow"
      Sid    = ""
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  provider = aws.target
  name     = "${local.name}-lambda"
  role     = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParameterHistory"
        ]
        Resource = compact([
          var.ssm_slack_token_arn,
          var.ssm_grafana_token_arn
        ])
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:GetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:BatchGetItem",
          "dynamodb:Query",
          "dynamodb:DescribeTable",
          "dynamodb:TransactWriteItems",
          "dynamodb:ConditionCheckItem"
        ]
        Resource = [
          aws_dynamodb_table.keda_scale_table.arn,
          "${aws_dynamodb_table.keda_scale_table.arn}/index/*"
        ]
      }

    ]
  })
}

