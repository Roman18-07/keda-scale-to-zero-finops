provider "aws" {
  alias  = "target"
  region = var.aws_region

  dynamic "assume_role" {
    for_each = var.target_account_deploy_role != "" ? [1] : []
    content {
      role_arn     = var.target_account_deploy_role
      session_name = "${var.environment}-keda-scale-to-zero"
    }
  }

  default_tags {
    tags = merge({
      Source      = "managed-by-terraform"
      Repo        = "keda-scale-to-zero"
      Environment = var.environment
      Application = var.application
    }, var.extra_tags)
  }
}
