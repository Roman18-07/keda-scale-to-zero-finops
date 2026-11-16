resource "null_resource" "change_on_lambda_src_change" {
  triggers = {
    run_always = local.lambda_src_hash
  }
}

# We need to trigger replace of this resource on src change. Otherwise it will not run during apply phase
resource "archive_file" "lambda_dist_zip" {
  type       = "zip"
  source_dir = "${path.module}/lambda_src"
  # output_path = "${path.module}/lambda_dist/lambda_function.zip"
  output_path = abspath("${path.module}/lambda_dist/lambda_function.zip")

  lifecycle {
    replace_triggered_by = [
      null_resource.change_on_lambda_src_change
    ]
  }
}

