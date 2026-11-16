resource "aws_iam_role" "apps_keda" {
  provider = aws.target

  name        = "${var.environment}-apps-${var.application}"
  description = "EKS apps pods role"

  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : data.aws_iam_openid_connect_provider.apps_eks_openid.arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${replace(data.aws_iam_openid_connect_provider.apps_eks_openid.url, "https://", "")}:sub" : "system:serviceaccount:${var.application}:keda-operator"
          }
        }
      }
    ]
  })

  depends_on = [
    data.aws_iam_openid_connect_provider.apps_eks_openid
  ]
}

resource "aws_iam_policy" "apps_keda_dynamodb" {
  count    = var.enable_scale_to_zero ? 1 : 0
  provider = aws.target
  name     = "${var.environment}-apps-${var.application}-dynamodb"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect : "Allow",
      Action : [
        "dynamodb:DescribeTable",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:GetItem"
      ],
      Resource : [
        module.scale_to_zero[0].ddb_table_arn,
        "${module.scale_to_zero[0].ddb_table_arn}/index/*",
        module.scale_to_zero_jhub[0].ddb_table_arn,
        "${module.scale_to_zero_jhub[0].ddb_table_arn}/index/*"
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "apps_keda_dynamodb" {
  count      = var.enable_scale_to_zero ? 1 : 0
  provider   = aws.target
  role       = aws_iam_role.apps_keda.name
  policy_arn = aws_iam_policy.apps_keda_dynamodb[0].arn
}


