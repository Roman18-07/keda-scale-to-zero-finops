locals {
  name = "${var.environment}-${var.application}-scale-to-zero"

  # Lambda
  lambda_src_path  = "${path.module}/lambda_src"
  lambda_src_files = fileset(local.lambda_src_path, "**")
  lambda_src_hash = md5(join("", [
    for f in local.lambda_src_files : filemd5("${local.lambda_src_path}/${f}")
  ]))
}
