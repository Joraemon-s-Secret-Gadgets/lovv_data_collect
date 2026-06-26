output "bucket_name" {
  # Phase 0/운영에서 생성된 파이프라인 S3 버킷 식별자
  description = "Pipeline artifact bucket name."
  value       = aws_s3_bucket.pipeline.bucket
}

output "bucket_arn" {
  # 버킷 ARN (IAM 정책 연동 또는 외부 참조에 사용).
  description = "Pipeline artifact bucket ARN."
  value       = aws_s3_bucket.pipeline.arn
}

output "domain_dynamodb_table_name" {
  # 음식점/관광지/축제 분리 전처리 결과를 적재할 신규 테이블 이름.
  description = "Domain-separated KR content table."
  value       = aws_dynamodb_table.tourkorea_domain_data.name
}

output "domain_dynamodb_table_arn" {
  # 신규 도메인 분리 테이블 ARN.
  description = "Domain-separated KR content table ARN."
  value       = aws_dynamodb_table.tourkorea_domain_data.arn
}

output "lambda_role_arn" {
  # 다음 단계 Lambda 생성 시 재사용할 IAM 역할 ARN.
  description = "IAM role for pipeline lambdas."
  value       = aws_iam_role.pipeline_lambda_role.arn
}

output "kr_pipeline_transform_lambda_name" {
  # kr-pipeline-transform Lambda function name (formerly kr-domain-loader).
  description = "Name of deployed KR pipeline transform Lambda function."
  value       = aws_lambda_function.kr_pipeline_transform.function_name
}

output "kr_pipeline_transform_lambda_arn" {
  # kr-pipeline-transform Lambda ARN.
  description = "ARN of deployed KR pipeline transform Lambda function."
  value       = aws_lambda_function.kr_pipeline_transform.arn
}

output "kr_pipeline_vector_lambda_name" {
  # kr-pipeline-vector Lambda function name (formerly kr-vector-index).
  description = "Name of deployed KR pipeline vector Lambda function."
  value       = aws_lambda_function.kr_pipeline_vector.function_name
}

output "kr_pipeline_vector_lambda_arn" {
  # kr-pipeline-vector Lambda ARN.
  description = "ARN of deployed KR pipeline vector Lambda function."
  value       = aws_lambda_function.kr_pipeline_vector.arn
}

output "vector_bucket_name" {
  # S3 Vector bucket name used by the KR vector index.
  description = "S3 Vector bucket name for KR vector indexes."
  value       = var.vector_bucket_name
}

output "kr_vector_index_name" {
  # S3 Vector index name used for KR tourism domain search.
  description = "S3 Vector index name for KR tourism domain data."
  value       = var.kr_vector_index_name
}

output "kr_vector_index_arn" {
  # S3 Vector index ARN for writer/reader policy references.
  description = "ARN of the KR S3 Vector index."
  value       = local.kr_vector_index_arn
}

output "s3_vector_index_writer_role_arn" {
  # Role for index build/upsert jobs.
  description = "IAM role ARN for S3 Vector index writer jobs."
  value       = aws_iam_role.s3_vector_index_writer_role.arn
}

output "s3_vector_index_reader_role_arn" {
  # Role for Candidate Evidence Agent retrieval queries.
  description = "IAM role ARN for S3 Vector index reader queries."
  value       = aws_iam_role.s3_vector_index_reader_role.arn
}
