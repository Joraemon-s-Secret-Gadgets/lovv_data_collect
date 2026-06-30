# -----------------------------------------------------------------------------
# kr-pipeline-image Lambda — 도시 단위 이미지 다운로드/S3 업로드 전담
# -----------------------------------------------------------------------------
# 신규 Lambda: Step Functions Map State에서 도시별로 병렬 호출됩니다.
# 외부 CDN 이미지를 다운로드하여 이미지 전용 S3 버킷에 적재하고,
# image_url을 S3 URL로 치환한 결과를 출력합니다.

# -----------------------------------------------------------------------------
# Archive: kr_image_processor 소스 ZIP
# -----------------------------------------------------------------------------
data "archive_file" "kr_image_processor_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/kr_image_processor_lambda.zip"
  excludes = [
    "**/__pycache__/**",
    "**/tests/**",
    "kr_details_pipeline/**",
    "kr_unified_pipeline/**",
    "kr_vector_index/**",
  ]
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda_image" {
  # kr-pipeline-image Lambda 런타임 로그. 보관 기간은 14일.
  name              = "/aws/lambda/${local.lambda_names.image}"
  retention_in_days = 14
}

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "kr_pipeline_image" {
  function_name    = local.lambda_names.image
  description      = "KR pipeline image processor Lambda for city-level image download and S3 upload"
  role             = aws_iam_role.pipeline_lambda_role.arn
  handler          = "kr_image_processor.handlers.image_handler.handler"
  runtime          = "python3.12"
  timeout          = 900
  memory_size      = 512
  filename         = data.archive_file.kr_image_processor_lambda.output_path
  source_code_hash = data.archive_file.kr_image_processor_lambda.output_base64sha256

  layers = [
    aws_lambda_layer_version.requests.arn,
  ]

  environment {
    variables = {
      IMAGE_BUCKET    = aws_s3_bucket.pipeline_images.bucket
      PIPELINE_BUCKET = aws_s3_bucket.pipeline.bucket
    }
  }

  depends_on = [
    aws_iam_role_policy.pipeline_lambda_policy,
    aws_cloudwatch_log_group.lambda_image,
  ]
}
