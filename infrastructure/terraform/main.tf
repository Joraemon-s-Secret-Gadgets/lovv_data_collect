# -----------------------------------------------------------------------------
# Runtime context
# -----------------------------------------------------------------------------
# 현재 AWS 계정 ID를 읽어오기 위해 caller identity를 조회해
# 리소스 명명/ARN 구성 시 일관된 식별값(account_id)을 사용합니다.
data "aws_caller_identity" "current" {}

# -----------------------------------------------------------------------------
# 공통 유틸리티 값
# -----------------------------------------------------------------------------
# 버킷명은 환경명과 계정 ID를 결합해 고유하게 생성합니다.
# Lambda 이름은 stage 간 구분을 위해 로컬 맵으로 관리합니다.
# 태그는 사용자 태그에 env를 덮어써서 환경 정합성을 보장합니다.
locals {
  bucket_name = "${var.bucket_base_name}-${var.env}-${data.aws_caller_identity.current.account_id}"
  lambda_names = {
    transform = "kr-pipeline-transform"
    loader    = "kr-pipeline-loader"
    vector    = "kr-pipeline-vector"
    ingest    = "kr-pipeline-ingest"
    image     = "kr-pipeline-image"
  }
  vector_bucket_arn              = "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${var.vector_bucket_name}"
  kr_vector_index_arn            = "${local.vector_bucket_arn}/index/${var.kr_vector_index_name}"
  agentcore_v1_vector_bucket_arn = "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${var.agentcore_v1_vector_bucket_name}"
  agentcore_v1_vector_index_arn  = "${local.agentcore_v1_vector_bucket_arn}/index/${var.agentcore_v1_vector_index_name}"
  kr_vector_index_create_input = jsonencode({
    vectorBucketName = var.vector_bucket_name
    indexName        = var.kr_vector_index_name
    dataType         = var.kr_vector_index_data_type
    dimension        = var.kr_vector_index_dimension
    distanceMetric   = var.kr_vector_index_distance_metric
    metadataConfiguration = {
      nonFilterableMetadataKeys = var.kr_vector_index_non_filterable_metadata_keys
    }
    encryptionConfiguration = {
      sseType = "AES256"
    }
  })
  base_tags = merge(var.tags, { env = var.env })
}

resource "terraform_data" "kr_vector_index" {
  input = {
    aws_profile        = var.aws_profile
    aws_region         = var.aws_region
    create_input       = local.kr_vector_index_create_input
    data_type          = var.kr_vector_index_data_type
    dimension          = var.kr_vector_index_dimension
    distance_metric    = var.kr_vector_index_distance_metric
    index_name         = var.kr_vector_index_name
    metadata_keys      = join(",", var.kr_vector_index_non_filterable_metadata_keys)
    vector_bucket_name = var.vector_bucket_name
  }

  triggers_replace = [
    var.aws_profile,
    var.aws_region,
    var.vector_bucket_name,
    var.kr_vector_index_name,
    var.kr_vector_index_data_type,
    tostring(var.kr_vector_index_dimension),
    var.kr_vector_index_distance_metric,
    join(",", var.kr_vector_index_non_filterable_metadata_keys),
  ]

  provisioner "local-exec" {
    interpreter = ["PowerShell", "-NoProfile", "-Command"]
    command     = <<-EOT
      aws s3vectors get-index --profile '${self.input.aws_profile}' --region '${self.input.aws_region}' --vector-bucket-name '${self.input.vector_bucket_name}' --index-name '${self.input.index_name}' --output json *> $null
      if ($LASTEXITCODE -eq 0) {
        Write-Host 'S3 Vector index already exists.'
        exit 0
      }
      aws s3vectors create-index --profile '${self.input.aws_profile}' --region '${self.input.aws_region}' --cli-input-json $env:KR_VECTOR_INDEX_CREATE_INPUT --output json
      if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
      }
    EOT

    environment = {
      KR_VECTOR_INDEX_CREATE_INPUT = self.input.create_input
    }
  }

  provisioner "local-exec" {
    when        = destroy
    interpreter = ["PowerShell", "-NoProfile", "-Command"]
    command     = <<-EOT
      aws s3vectors get-index --profile '${self.input.aws_profile}' --region '${self.input.aws_region}' --vector-bucket-name '${self.input.vector_bucket_name}' --index-name '${self.input.index_name}' --output json *> $null
      if ($LASTEXITCODE -ne 0) {
        exit 0
      }
      aws s3vectors delete-index --profile '${self.input.aws_profile}' --region '${self.input.aws_region}' --vector-bucket-name '${self.input.vector_bucket_name}' --index-name '${self.input.index_name}'
      if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
      }
    EOT
  }
}

resource "aws_s3_bucket" "pipeline" {
  # 수집된 원천/가공 데이터가 들어갈 파이프라인 저장소입니다.
  bucket        = local.bucket_name
  force_destroy = false

  tags = merge(local.base_tags, { Name = local.bucket_name })
}

resource "aws_s3_bucket_versioning" "pipeline" {
  # 객체 버전관리를 활성화해 실수/변경 이력 복원이 가능하도록 합니다.
  bucket = aws_s3_bucket.pipeline.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pipeline" {
  # 저장 시 기본 SSE(AES256) 적용으로 저장 데이터 기초 보호를 강화합니다.
  bucket = aws_s3_bucket.pipeline.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "pipeline" {
  # 퍼블릭 접근이 차단되도록 모든 퍼블릭-차단 스위치를 ON으로 설정합니다.
  bucket                  = aws_s3_bucket.pipeline.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "pipeline" {
  # 원천 데이터 보관 정책:
  # 30일 후 STANDARD_IA, 60일 후 GLACIER로 이동합니다.
  bucket = aws_s3_bucket.pipeline.id

  rule {
    id     = "raw-cold-storage"
    status = "Enabled"

    filter {
      prefix = "${var.raw_data_prefix}/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 60
      storage_class = "GLACIER"
    }
  }
}

resource "aws_dynamodb_table" "tourkorea_domain_data" {
  # 음식점/관광지/축제를 분리한 전처리 결과를 적재하는 도메인 테이블입니다.
  name           = var.domain_dynamodb_table_name
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"
  stream_enabled = false

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "entity_type"
    type = "S"
  }

  attribute {
    name = "city_key"
    type = "S"
  }

  attribute {
    name = "province_key"
    type = "S"
  }

  attribute {
    name = "domain_sort_key"
    type = "S"
  }

  global_secondary_index {
    name            = "GSI1"
    hash_key        = "city_key"
    range_key       = "domain_sort_key"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "GSI2"
    hash_key        = "province_key"
    range_key       = "domain_sort_key"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "GSI3"
    hash_key        = "entity_type"
    range_key       = "domain_sort_key"
    projection_type = "ALL"
  }

  # 축제 월별 조회 GSI (Bedrock Metadata Enrichment)
  # entity_type="festival" + gsi_sk begins_with "FESTIVAL#{month:02d}" 로 range query
  attribute {
    name = "gsi_sk"
    type = "S"
  }

  global_secondary_index {
    name            = "FestivalMonthIndex"
    hash_key        = "entity_type"
    range_key       = "gsi_sk"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.base_tags, { Name = var.domain_dynamodb_table_name, schema = "domain-separated" })
}

resource "aws_dynamodb_table" "tourkorea_domain_data_v2" {
  # 의미 있는 GSI 명명을 적용한 신규 도메인 테이블입니다.
  name                        = var.domain_dynamodb_table_name_v2
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "PK"
  range_key                   = "SK"
  stream_enabled              = false
  deletion_protection_enabled = false

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
  attribute {
    name = "entity_type"
    type = "S"
  }
  attribute {
    name = "city_key"
    type = "S"
  }
  attribute {
    name = "province_key"
    type = "S"
  }
  attribute {
    name = "domain_sort_key"
    type = "S"
  }
  attribute {
    name = "gsi_sk"
    type = "S"
  }

  global_secondary_index {
    name            = "CityDomainIndex"
    hash_key        = "city_key"
    range_key       = "domain_sort_key"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "ProvinceDomainIndex"
    hash_key        = "province_key"
    range_key       = "domain_sort_key"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "EntityTypeDomainIndex"
    hash_key        = "entity_type"
    range_key       = "domain_sort_key"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "FestivalMonthIndex"
    hash_key        = "entity_type"
    range_key       = "gsi_sk"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.base_tags, { Name = var.domain_dynamodb_table_name_v2, schema = "domain-separated-v2" })
}

resource "aws_iam_role" "pipeline_lambda_role" {
  # Lambda 실행 역할. Lambda 서비스가 AssumeRole로 사용합니다.
  name = "lovv-data-pipeline-lambda-${var.env}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.base_tags, { Name = "lovv-data-pipeline-lambda-role-${var.env}" })
}

resource "aws_iam_role_policy" "pipeline_lambda_policy" {
  # Lambda 기능에 필요한 최소 권한을 인라인으로 제한합니다.
  # 현재 단계에서는 DynamoDB, S3, CloudWatch Logs, Bedrock, S3 Vector만 허용합니다.
  name = "lovv-data-pipeline-lambda-policy-${var.env}"
  role = aws_iam_role.pipeline_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.tourkorea_domain_data.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.tourkorea_domain_data_v2.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query"
        ]
        Resource = "${aws_dynamodb_table.tourkorea_domain_data_v2.arn}/index/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable"
        ]
        Resource = aws_dynamodb_table.tourkorea_domain_data_v2.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query"
        ]
        Resource = "${aws_dynamodb_table.tourkorea_domain_data.arn}/index/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable"
        ]
        Resource = aws_dynamodb_table.tourkorea_domain_data.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.tourkorea_domain_data_v2.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query"
        ]
        Resource = "${aws_dynamodb_table.tourkorea_domain_data_v2.arn}/index/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable"
        ]
        Resource = aws_dynamodb_table.tourkorea_domain_data_v2.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.pipeline.arn,
          "${aws_s3_bucket.pipeline.arn}/*",
          aws_s3_bucket.pipeline_images.arn,
          "${aws_s3_bucket.pipeline_images.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
      },
      {
        # Bedrock Converse API for attraction enrichment & festival theme classification
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3vectors:GetVectorBucket",
          "s3vectors:GetIndex",
          "s3vectors:ListVectors",
          "s3vectors:GetVectors",
          "s3vectors:QueryVectors",
          "s3vectors:PutVectors"
        ]
        Resource = [
          local.vector_bucket_arn,
          local.kr_vector_index_arn
        ]
      },
      {
        # AgentCore v1 vector bucket/index (강원/경북 전용)
        Effect = "Allow"
        Action = [
          "s3vectors:GetVectorBucket",
          "s3vectors:GetIndex",
          "s3vectors:ListVectors",
          "s3vectors:GetVectors",
          "s3vectors:QueryVectors",
          "s3vectors:PutVectors"
        ]
        Resource = [
          local.agentcore_v1_vector_bucket_arn,
          local.agentcore_v1_vector_index_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role" "s3_vector_index_writer_role" {
  # S3 Vector index build pipeline role. It can write vectors and run verification queries.
  name = "lovv-vector-index-writer-${var.env}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
      }
    ]
  })

  tags = merge(local.base_tags, { Name = "lovv-vector-index-writer-${var.env}", scope = "s3-vector-writer" })
}

resource "aws_iam_role_policy" "s3_vector_index_writer_policy" {
  # Writer can build, repair, and verify the vector index, but cannot create/delete vector buckets or indexes.
  name = "lovv-vector-index-writer-policy-${var.env}"
  role = aws_iam_role.s3_vector_index_writer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3vectors:GetVectorBucket",
          "s3vectors:GetIndex",
          "s3vectors:ListIndexes",
          "s3vectors:ListVectors",
          "s3vectors:GetVectors",
          "s3vectors:QueryVectors",
          "s3vectors:PutVectors"
        ]
        Resource = [
          local.vector_bucket_arn,
          local.kr_vector_index_arn,
          local.agentcore_v1_vector_bucket_arn,
          local.agentcore_v1_vector_index_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role" "s3_vector_index_reader_role" {
  # Candidate Evidence Agent retrieval role. It can query the index but cannot mutate vectors.
  name = "lovv-vector-index-reader-${var.env}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
      }
    ]
  })

  tags = merge(local.base_tags, { Name = "lovv-vector-index-reader-${var.env}", scope = "s3-vector-reader" })
}

resource "aws_iam_role_policy" "s3_vector_index_reader_policy" {
  # Reader is intentionally query-only for CEA retrieval. Mutating actions are excluded.
  name = "lovv-vector-index-reader-policy-${var.env}"
  role = aws_iam_role.s3_vector_index_reader_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3vectors:GetVectorBucket",
          "s3vectors:GetIndex",
          "s3vectors:QueryVectors"
        ]
        Resource = [
          local.vector_bucket_arn,
          local.kr_vector_index_arn,
          local.agentcore_v1_vector_bucket_arn,
          local.agentcore_v1_vector_index_arn
        ]
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda_transform" {
  # kr-pipeline-transform Lambda 런타임 로그. 보관 기간은 14일.
  name              = "/aws/lambda/${local.lambda_names.transform}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda_vector" {
  # kr-pipeline-vector Lambda 런타임 로그. 보관 기간은 14일.
  name              = "/aws/lambda/${local.lambda_names.vector}"
  retention_in_days = 14
}

data "archive_file" "kr_pipeline_lambda" {
  # 현재 패키지는 `src/` 전체를 ZIP으로 묶어 Lambda에서 공통 handler를 로드합니다.
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/kr_pipeline_lambda.zip"
  excludes = [
    "**/__pycache__/**",
    "**/tests/**",
    "kr_vector_index/**",
  ]
}

data "archive_file" "kr_vector_index_lambda" {
  # S3 Vector index handler만 별도 ZIP으로 묶어 domain-loader 재배포를 피합니다.
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/kr_vector_index_lambda.zip"
  excludes = [
    "**/__pycache__/**",
    "**/tests/**",
    "kr_details_pipeline/**",
    "kr_vector_index/live_verification.py",
    "kr_vector_index/live_verification_cli.py",
    "kr_vector_index/terraform_plan_guard.py",
    "kr_vector_index/terraform_plan_guard_cli.py",
  ]
}

resource "aws_lambda_function" "kr_pipeline_transform" {
  function_name    = local.lambda_names.transform
  description      = "KR pipeline transform Lambda for manual raw JSON preprocessing and DynamoDB load"
  role             = aws_iam_role.pipeline_lambda_role.arn
  handler          = "kr_details_pipeline.handlers.domain_loader_handler.handler"
  runtime          = "python3.12"
  timeout          = 900
  memory_size      = 1024
  filename         = data.archive_file.kr_pipeline_lambda.output_path
  source_code_hash = data.archive_file.kr_pipeline_lambda.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE   = var.domain_dynamodb_table_name_v2
      IMAGE_BUCKET     = aws_s3_bucket.pipeline_images.bucket
      PROCESSED_PREFIX = "${var.processed_data_prefix}/details"
    }
  }

  depends_on = [
    aws_iam_role_policy.pipeline_lambda_policy,
    aws_cloudwatch_log_group.lambda_transform,
  ]
}

resource "aws_lambda_function" "kr_pipeline_vector" {
  function_name    = local.lambda_names.vector
  description      = "KR S3 Vector index build Lambda handler"
  role             = aws_iam_role.pipeline_lambda_role.arn
  handler          = "kr_vector_index.handlers.vector_index_handler.handler"
  runtime          = "python3.12"
  timeout          = 900
  memory_size      = 1024
  filename         = data.archive_file.kr_vector_index_lambda.output_path
  source_code_hash = data.archive_file.kr_vector_index_lambda.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE  = var.domain_dynamodb_table_name_v2
      VECTOR_BUCKET   = var.vector_bucket_name
      VECTOR_INDEX    = var.kr_vector_index_name
      MANIFEST_BUCKET = aws_s3_bucket.pipeline.bucket
      MANIFEST_PREFIX = "${var.processed_data_prefix}/vector/manifests"
    }
  }

  depends_on = [
    aws_iam_role_policy.pipeline_lambda_policy,
    aws_cloudwatch_log_group.lambda_vector,
  ]
}

# -----------------------------------------------------------------------------
# kr-pipeline-loader Lambda (기존 kr_unified_pipeline 코드 재사용)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "lambda_loader" {
  # kr-pipeline-loader Lambda 런타임 로그. 보관 기간은 14일.
  name              = "/aws/lambda/${local.lambda_names.loader}"
  retention_in_days = 14
}

data "archive_file" "kr_unified_pipeline_lambda" {
  # kr_unified_pipeline 소스를 ZIP으로 묶어 loader Lambda에 배포합니다.
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/kr_unified_pipeline_lambda.zip"
  excludes = [
    "**/__pycache__/**",
    "**/tests/**",
    "kr_vector_index/**",
    "kr_image_processor/**",
  ]
}

resource "aws_lambda_function" "kr_pipeline_loader" {
  function_name    = local.lambda_names.loader
  description      = "KR pipeline loader Lambda for S3-to-DynamoDB load"
  role             = aws_iam_role.pipeline_lambda_role.arn
  handler          = "kr_unified_pipeline.handlers.pipeline_handler.handler"
  runtime          = "python3.12"
  timeout          = 900
  memory_size      = 512
  filename         = data.archive_file.kr_unified_pipeline_lambda.output_path
  source_code_hash = data.archive_file.kr_unified_pipeline_lambda.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE   = var.domain_dynamodb_table_name_v2
      PIPELINE_BUCKET  = aws_s3_bucket.pipeline.bucket
      PROCESSED_PREFIX = var.processed_data_prefix
    }
  }

  depends_on = [
    aws_iam_role_policy.pipeline_lambda_policy,
    aws_cloudwatch_log_group.lambda_loader,
  ]
}
