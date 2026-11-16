resource "aws_dynamodb_table" "keda_scale_table" {
  provider     = aws.target
  name         = "${local.name}-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "session_id"

  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "session_id"
    type = "S"
  }
  attribute {
    name = "gsi_pk"
    type = "S"
  }
  attribute {
    name = "expires_at"
    type = "N"
  }
  attribute {
    name = "next_ping_at"
    type = "N"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery { enabled = true }

  global_secondary_index {
    name            = "gsi_due"
    hash_key        = "gsi_pk"
    range_key       = "next_ping_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "gsi_expire"
    hash_key        = "gsi_pk"
    range_key       = "expires_at"
    projection_type = "ALL"
  }

  tags = {
    Name        = "${local.name}-sessions"
    Environment = var.environment
    Application = var.application
    ManagedBy   = "terraform"
  }
}
