# -----------------------------------------------------------------------------
# 공통 배포 설정
# -----------------------------------------------------------------------------
variable "aws_region" {
  description = "AWS region for this pipeline."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile used by Terraform."
  type        = string
  default     = "skn26_final"
}

variable "env" {
  description = "Deployment environment (dev/stg/prod)."
  type        = string
  default     = "dev"
}

# -----------------------------------------------------------------------------
# S3 관련 접두사: 저장 위치 규칙을 기능별로 분리합니다.
# -----------------------------------------------------------------------------
variable "bucket_base_name" {
  description = "S3 bucket name prefix for pipeline artifacts."
  type        = string
  default     = "lovv-data-pipeline"
}

variable "raw_data_prefix" {
  description = "Base prefix for KR raw input files."
  type        = string
  default     = "raw/KR"
}

variable "processed_data_prefix" {
  description = "Base prefix for processed objects."
  type        = string
  default     = "processed/KR"
}

variable "failed_data_prefix" {
  description = "Base prefix for failed objects."
  type        = string
  default     = "failed/KR"
}

variable "review_data_prefix" {
  description = "Base prefix for manual/auto review queue payloads."
  type        = string
  default     = "review"
}

variable "quality_prefix" {
  description = "Base prefix for quality report payloads."
  type        = string
  default     = "quality/KR"
}

variable "vector_bucket_name" {
  description = "S3 Vector bucket name for KR vector indexes."
  type        = string
  default     = "lovv-vector-dev"
}

variable "kr_vector_index_name" {
  description = "S3 Vector index name for KR tourism domain data V2."
  type        = string
  default     = "kr-tour-domain-v2"
}

variable "kr_vector_index_data_type" {
  description = "S3 Vector index vector data type for KR tourism domain data V2."
  type        = string
  default     = "float32"

  validation {
    condition     = contains(["float32"], var.kr_vector_index_data_type)
    error_message = "KR vector index data type must be float32."
  }
}

variable "kr_vector_index_dimension" {
  description = "S3 Vector index embedding dimension for KR tourism domain data V2."
  type        = number
  default     = 1024

  validation {
    condition     = var.kr_vector_index_dimension > 0
    error_message = "KR vector index dimension must be greater than 0."
  }
}

variable "kr_vector_index_distance_metric" {
  description = "S3 Vector index distance metric for KR tourism domain data V2."
  type        = string
  default     = "cosine"

  validation {
    condition     = contains(["cosine", "euclidean"], var.kr_vector_index_distance_metric)
    error_message = "KR vector index distance metric must be cosine or euclidean."
  }
}

variable "kr_vector_index_non_filterable_metadata_keys" {
  description = "S3 Vector index metadata keys that should not be filterable for KR tourism domain data V2."
  type        = list(string)
  default     = ["raw_s3_uri", "ddb_pk", "ddb_sk", "embedding_model"]
}

variable "kr_vector_batch_size" {
  description = "Maximum number of vectorizable DynamoDB items processed by one KR vector worker invocation."
  type        = number
  default     = 250

  validation {
    condition     = var.kr_vector_batch_size > 0 && var.kr_vector_batch_size <= 500
    error_message = "KR vector batch size must be between 1 and 500."
  }
}

variable "kr_vector_map_max_concurrency" {
  description = "Maximum concurrent KR vector worker invocations in the Step Functions Map state."
  type        = number
  default     = 5

  validation {
    condition     = var.kr_vector_map_max_concurrency > 0 && var.kr_vector_map_max_concurrency <= 40
    error_message = "KR vector map max concurrency must be between 1 and 40."
  }
}

# -----------------------------------------------------------------------------
# AgentCore v1 Vector 구성 (강원/경북 전용)
# -----------------------------------------------------------------------------
variable "agentcore_v1_vector_bucket_name" {
  description = "S3 Vector bucket name for AgentCore v1 (강원/경북 only)."
  type        = string
  default     = "lovv-agentcore-v1-vector"
}

variable "agentcore_v1_vector_index_name" {
  description = "S3 Vector index name for AgentCore v1."
  type        = string
  default     = "kr-agentcore-v1"
}

# -----------------------------------------------------------------------------
# 데이터 저장소(DynamoDB) 구성
# -----------------------------------------------------------------------------
variable "domain_dynamodb_table_name" {
  description = "DynamoDB table name for domain-separated KR content data."
  type        = string
  default     = "TourKoreaDomainData"
}

variable "domain_dynamodb_table_name_v2" {
  description = "DynamoDB V2 table name with descriptive GSI naming for unified pipeline."
  type        = string
  default     = "TourKoreaDomainDataV2"
}

# -----------------------------------------------------------------------------
# 리소스 공통 태그
# -----------------------------------------------------------------------------
variable "tags" {
  description = "Common tags for all resources."
  type        = map(string)
  default = {
    project = "lovv"
    app     = "data-pipeline"
    env     = "dev"
    managed = "terraform"
    phase   = "phase0"
  }
}
