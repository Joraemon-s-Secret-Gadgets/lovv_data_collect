# Implementation Plan: kr-data-pipeline

## Overview

AWS Step Functions 상태 머신으로 211개 도시 관광 데이터를 End-to-End 처리하는 파이프라인 구현. 기존 Lambda 3개를 `kr-pipeline-*` prefix로 이름 변경하고, 신규 `kr-pipeline-image` Lambda를 추가하여 도시 단위 병렬 이미지 처리를 수행한다. Terraform으로 모든 인프라를 정의하며, Python 3.12 런타임을 사용한다.

## Tasks

- [x] 1. Lambda 이름 변경 및 인프라 기초 정리
  - [x] 1.1 Update `locals.lambda_names` map in `main.tf` to reflect new names
    - Change `domain_loader = "kr-domain-loader"` → `transform = "kr-pipeline-transform"`
    - Change `vector_index = "kr-vector-index"` → `vector = "kr-pipeline-vector"`
    - Add `loader = "kr-pipeline-loader"`, `ingest = "kr-pipeline-ingest"`, `image = "kr-pipeline-image"`
    - Update all `local.lambda_names.*` references in `main.tf` (resource names, function_name, log groups)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.7_

  - [x] 1.2 Rename Lambda function resources in `main.tf`
    - Rename `aws_lambda_function.kr_domain_loader` → `aws_lambda_function.kr_pipeline_transform`
    - Update function_name to `kr-pipeline-transform`, handler path unchanged
    - Rename `aws_lambda_function.kr_vector_index` → `aws_lambda_function.kr_pipeline_vector`
    - Update function_name to `kr-pipeline-vector`, handler path unchanged
    - Add new `aws_lambda_function.kr_pipeline_loader` resource for existing `kr_unified_pipeline` code
    - Add new `aws_lambda_function.kr_pipeline_ingest` resource for existing `kr-raw-ingest` code
    - Update CloudWatch Log Groups to match `/aws/lambda/kr-pipeline-*` naming
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 10.8, 10.9_

  - [x] 1.3 Create `infrastructure/terraform/image_bucket.tf` — new S3 bucket for pipeline images
    - Define `aws_s3_bucket.pipeline_images` with name `lovv-pipeline-images-${var.env}-${data.aws_caller_identity.current.account_id}`
    - Add `aws_s3_bucket_server_side_encryption_configuration` (SSE-S3 / AES256)
    - Add `aws_s3_bucket_public_access_block` (all blocks = true)
    - Versioning disabled (no versioning resource = disabled by default)
    - _Requirements: 9.1, 9.2_

- [ ] 2. Lambda Layer 및 신규 Lambda 인프라
  - [x] 2.1 Create `layers/requests/build.sh` — build script for requests Lambda Layer
    - Script: `pip install requests -t python/ --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12`
    - Zip output to `layer.zip`
    - Print layer size for validation (< 50MB)
    - _Requirements: 6.1, 6.2, 6.6_

  - [~] 2.2 Create `infrastructure/terraform/lambda_layer_requests.tf` — Terraform resource for Lambda Layer
    - Define `aws_lambda_layer_version.requests` resource
    - Compatible runtimes: `python3.12`
    - Compatible architectures: `x86_64`
    - Source: `layers/requests/layer.zip`
    - Attach to `kr-pipeline-image` Lambda
    - Attach to `kr-pipeline-loader` Lambda
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [~] 2.3 Create `infrastructure/terraform/lambda_image_processor.tf` — new kr-pipeline-image Lambda
    - Define `aws_lambda_function.kr_pipeline_image` resource
    - Runtime: python3.12, timeout: 900 (15min), memory: 512MB
    - Handler: `kr_image_processor.handlers.image_handler.handler`
    - Attach requests Lambda Layer
    - Define `aws_cloudwatch_log_group` with 14-day retention
    - IAM: S3 read on pipeline data bucket + S3 read/write on image bucket
    - _Requirements: 2.2, 6.3, 9.3_

- [~] 3. Checkpoint — Terraform infrastructure validation
  - Ensure `terraform plan` produces expected changes (no unintended modifications to existing resources).
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. kr-pipeline-image Lambda 구현 — 핵심 처리 로직
  - [x] 4.1 Create `src/kr_image_processor/__init__.py` and module directory structure
    - Create directories: `src/kr_image_processor/`, `src/kr_image_processor/handlers/`, `src/kr_image_processor/tests/`
    - Create `__init__.py` files for all packages
    - _Requirements: 2.2_

  - [~] 4.2 Implement `src/kr_image_processor/processor.py` — city-level image processing
    - Function `process_city(bucket, ingest_date, city_name_en, source_key)` → dict
    - Read city JSON from S3 (source_key)
    - For each record: download image via `kr_image_uploader.download.fetch_bytes` (3 retries with exponential backoff)
    - Upload to Image_Bucket at `images/KR/{city_name_en}/{filename}` using `kr_image_uploader.s3_keys.build_image_key`
    - Replace `image_url` with S3 URL, set `image_status: "ok"`
    - On failure: set `image_status: "needs_review"`, add to review entries
    - On empty/null image_url: classify `failure_reason: "no_source_image"`
    - Write output to `processed/KR/details/{ingest_date}/images/{city_name_en}.json`
    - Return summary dict with counts and review_entries list
    - Reuse `kr_image_uploader.romanize` for filename sanitization
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2_

  - [ ]* 4.3 Write property test for image URL replacement (Property 1)
    - **Property 1: Image URL Replacement**
    - Generate random city payloads with mock-successful downloads
    - Verify output `image_url` matches S3 URL pattern, original URL absent
    - **Validates: Requirements 2.4**

  - [ ]* 4.4 Write property test for failed downloads review classification (Property 2)
    - **Property 2: Failed Downloads Marked for Review**
    - Generate random payloads with mock-failed downloads
    - Verify `image_status == "needs_review"` and review entries contain `failure_reason: "download_failed"`
    - **Validates: Requirements 2.5, 3.2**

  - [ ]* 4.5 Write property test for empty image URL classification (Property 3)
    - **Property 3: Empty Image URL Classification**
    - Generate records with null/empty/whitespace `image_url`
    - Verify `failure_reason: "no_source_image"` in review entries
    - **Validates: Requirements 3.1**

  - [ ]* 4.6 Write property test for record count invariant (Property 7)
    - **Property 7: Record Count Invariant**
    - Generate random city payloads with N records
    - Verify sum of (processed ok + review entries) == N
    - **Validates: Requirements 2.3, 3.1**

- [ ] 5. kr-pipeline-image Lambda 구현 — Review 및 Report
  - [~] 5.1 Implement `src/kr_image_processor/review.py` — review manifest aggregation
    - Function `aggregate_review(bucket, ingest_date, image_results)` → dict
    - Collect all `review_entries` from per-city results
    - Write combined manifest to `processed/KR/review/{ingest_date}/image_review.json`
    - Each entry: city_name_en, content_id, entity_type, original_image_url, failure_reason, error_message, timestamp
    - _Requirements: 3.3, 3.4_

  - [ ]* 5.2 Write property test for review manifest entry completeness (Property 4)
    - **Property 4: Review Manifest Entry Completeness**
    - Generate any review-triggering record
    - Verify all required fields present: city_name_en, content_id, entity_type, original_image_url, failure_reason, timestamp
    - **Validates: Requirements 3.4**

  - [~] 5.3 Implement `src/kr_image_processor/report.py` — execution report generation
    - Function `generate_report(bucket, ingest_date, execution_context)` → dict
    - Aggregate per-city results into summary (total_cities, images_downloaded, images_failed, review_count, records_loaded, vectors_built)
    - Include per_city breakdown
    - Include failure_info if pipeline failed
    - Write to `processed/KR/reports/{ingest_date}/pipeline_report.json`
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 5.4 Write property test for output key path correctness (Property 5)
    - **Property 5: Output Key Path Correctness**
    - Generate random city names (ASCII alphanumeric + underscore) and dates (YYYYMMDD)
    - Verify output key matches `processed/KR/details/{ingest_date}/images/{city_name_en}.json`
    - **Validates: Requirements 2.8**

  - [ ]* 5.5 Write property test for execution report field completeness (Property 6)
    - **Property 6: Execution Report Field Completeness**
    - Generate random per-city result combinations
    - Verify report contains all required summary fields and all cities in per_city
    - **Validates: Requirements 8.2, 8.3**

- [ ] 6. kr-pipeline-image Lambda — Handler 통합
  - [~] 6.1 Implement `src/kr_image_processor/handlers/image_handler.py` — multi-command Lambda entry point
    - Route by `event["command"]`: `"process_city"` (default), `"aggregate_review"`, `"generate_report"`
    - `process_city`: call `processor.process_city()` with event params
    - `aggregate_review`: call `review.aggregate_review()` with event params
    - `generate_report`: call `report.generate_report()` with event params
    - Error handling: catch exceptions, return structured error response with statusCode 500
    - _Requirements: 2.2, 3.3, 8.1_

  - [ ]* 6.2 Write unit tests for handler command routing
    - Test each command dispatches to correct module
    - Test unknown command returns error
    - Test missing required params returns descriptive error
    - _Requirements: 2.2_

- [~] 7. Checkpoint — kr-pipeline-image Lambda 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Step Functions 상태 머신 구현
  - [~] 8.1 Create `infrastructure/terraform/step_functions.tf` — State Machine definition
    - Define `aws_sfn_state_machine.kr_data_pipeline` resource
    - ASL definition as per design (CheckSkipTransform → TransformStage → BuildCityList → ImageStage → AggregateReviewManifest → LoadStage → VectorStage → GenerateReport → Success)
    - Map State MaxConcurrency: 10 for TransformStage and ImageStage
    - Retry policies per design (transform: 2 attempts, image: 1 attempt, load: 2, vector: 1)
    - Catch blocks routing to HandleFailure → GenerateReport
    - VectorStage failure caught but non-fatal (routes to GenerateReport)
    - State machine name: `kr-data-pipeline-${var.env}`
    - Enable CloudWatch logging
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [~] 8.2 Define Step Functions IAM execution role in `step_functions.tf`
    - Create `aws_iam_role.sfn_execution_role` with states.amazonaws.com trust
    - Policy: invoke all 4 Lambda functions (transform, image, loader, vector)
    - Policy: CloudWatch Logs write for execution logging
    - _Requirements: 9.4, 9.5_

  - [ ]* 8.3 Write integration test for Step Functions ASL validation
    - Validate JSON structure of ASL definition
    - Verify all Lambda ARN references are correctly templated
    - Verify state transitions match design flow
    - _Requirements: 1.1, 1.7_

- [ ] 9. kr-pipeline-loader 수정 — prefix 파라미터 지원
  - [~] 9.1 Update `kr-pipeline-loader` Lambda's `load` command to accept alternative S3 prefix
    - Modify handler to accept `prefix` param in event (instead of hardcoded `passed/` path)
    - Default to existing behavior if prefix not provided (backward compatible)
    - When prefix is `processed/KR/details/{date}/images/`, load image-processed records
    - Preserve `image_status: "needs_review"` field when writing to DynamoDB
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 3.5_

  - [ ]* 9.2 Write unit tests for prefix parameter handling
    - Test load with explicit prefix
    - Test load with default prefix (backward compatibility)
    - Test records with `image_status: "needs_review"` are preserved
    - _Requirements: 4.2, 4.6_

- [ ] 10. DynamoDB V2 테이블 정리 스크립트
  - [~] 10.1 Create `scripts/cleanup_dynamodb_v2.py` — table delete & recreate script
    - Delete existing `TourKoreaDomainDataV2` table
    - Wait for deletion to complete
    - Recreate with same schema (PK, SK, GSIs) via Terraform apply or boto3
    - Print confirmation of empty table state
    - Include safety prompt (y/N) before execution
    - _Requirements: 9.8, 9.9_

- [~] 11. Checkpoint — 전체 인프라 및 통합 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Final wiring and deployment preparation
  - [~] 12.1 Create `data "archive_file"` for kr-pipeline-image Lambda in Terraform
    - Define ZIP archive for `src/kr_image_processor/` directory
    - Exclude `__pycache__`, `tests/`
    - Wire to `aws_lambda_function.kr_pipeline_image` resource
    - _Requirements: 2.2_

  - [~] 12.2 Update `infrastructure/terraform/outputs.tf` with new resource outputs
    - Add Step Functions state machine ARN output
    - Add kr-pipeline-image Lambda ARN output
    - Add image bucket name and ARN outputs
    - Add Lambda Layer ARN output
    - _Requirements: 1.5, 2.2, 9.1_

  - [~] 12.3 Ensure all IAM policies are complete and least-privilege
    - Verify kr-pipeline-image role has S3 read on data bucket + S3 read/write on image bucket
    - Verify Step Functions role invokes all 4 Lambdas
    - Verify existing kr-pipeline-loader role retains current permissions (no changes needed per Req 9.6)
    - Add new resources without modifying existing Lambda functions or buckets (Req 9.7)
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.7_

- [~] 13. Final checkpoint — 전체 프로젝트 검증
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Hypothesis, Python)
- Unit tests validate specific examples and edge cases
- Lambda handler code paths remain unchanged during rename — only `function_name` in Terraform changes
- The `kr_image_uploader` module is reused for download/upload logic (no duplication)
- Terraform destroy+create is required for Lambda rename (Lambda does not support in-place rename)
- All new Terraform resources go in separate `.tf` files — `main.tf` is modified only for `locals` and existing resource renames

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "4.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "4.2"] },
    { "id": 4, "tasks": ["4.3", "4.4", "4.5", "4.6", "5.1", "5.3"] },
    { "id": 5, "tasks": ["5.2", "5.4", "5.5", "6.1"] },
    { "id": 6, "tasks": ["6.2", "8.1", "9.1", "10.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "9.2"] },
    { "id": 8, "tasks": ["12.1", "12.2", "12.3"] }
  ]
}
```
