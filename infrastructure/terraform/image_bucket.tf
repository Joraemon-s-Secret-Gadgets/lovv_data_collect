# -----------------------------------------------------------------------------
# 이미지 전용 S3 버킷
# -----------------------------------------------------------------------------
# 파이프라인에서 다운로드한 이미지를 저장하는 전용 버킷입니다.
# 기존 앱 이미지 버킷과 완전히 분리된 별도 버킷으로 운영합니다.

resource "aws_s3_bucket" "pipeline_images" {
  # 파이프라인 이미지 저장소. 환경명+계정 ID로 고유 이름을 보장합니다.
  bucket        = "lovv-pipeline-images-${var.env}-${data.aws_caller_identity.current.account_id}"
  force_destroy = false

  tags = merge(local.base_tags, { Name = "lovv-pipeline-images-${var.env}-${data.aws_caller_identity.current.account_id}" })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pipeline_images" {
  # 저장 시 기본 SSE(AES256) 적용으로 이미지 데이터 보호를 강화합니다.
  bucket = aws_s3_bucket.pipeline_images.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "pipeline_images" {
  # 퍼블릭 접근이 차단되도록 모든 퍼블릭-차단 스위치를 ON으로 설정합니다.
  bucket                  = aws_s3_bucket.pipeline_images.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
