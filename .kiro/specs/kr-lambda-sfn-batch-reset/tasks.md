# Implementation Plan: kr-lambda-sfn-batch-reset

## Overview

이 계획은 KR 파이프라인의 Lambda 및 Step Functions 실행 계층을 Terraform 기준으로 재구성하는 순서를 정의한다. 작업 모드는 Sequential Mode를 사용한다. DynamoDB/S3 보호, Terraform plan 검토, live AWS drift 검증, `visitor_statistics` coverage 보완, 현재 브랜치 `investigate/enrichment-field-loading-20260628`의 enrichment field loading 보존, Step Functions Map 기반 vector batch smoke test가 핵심 gate다.

## Tasks

- [ ] 1. Spec approval and destructive boundary confirmation
  - [ ] 1.1 Review this Kiro spec with the user
    - Confirm protected resources: DynamoDB, S3 buckets, S3 objects, existing S3 Vector indexes
    - Confirm reset target: Lambda, Lambda layers, Step Functions, IAM execution policies
    - Confirm that manual console deletion is not allowed
    - Confirm that `terraform apply` requires a separate approval
    - _Requirements: 1.1-1.6, 5.1-5.6_

  - [ ] 1.2 Confirm vector rebuild operating target
    - Confirm target vector bucket
    - Confirm target vector index
    - Confirm whether existing `kr-tour-domain-v2` can be reused, recreated, or replaced by a dated index
    - Confirm initial batch size and Map concurrency
    - _Requirements: 7.1-7.10_

  - [x] 1.3 Confirm non-negotiable data completeness scope
    - Confirm `visitor_statistics` coverage must remain in the reset goal
    - Confirm the branch intent from `investigate/enrichment-field-loading-20260628` must remain in the reset goal
    - Confirm `visitor_statistics` is a DynamoDB/DataLab coverage concern, not a vector rebuild fix path
    - Confirm enrichment loading/backfill status must be reported before full vector rebuild
    - _Requirements: 3.1-3.9, 4.1-4.9_

- [x] 2. Capture live baseline and drift report
  - [x] 2.1 Capture live Lambda configuration
    - Read `kr-pipeline-transform`
    - Read `kr-pipeline-image`
    - Read `kr-pipeline-loader`
    - Read `kr-pipeline-vector`
    - Record handler, runtime, timeout, memory, layers, environment variables, code hash
    - _Requirements: 2.1, 2.3_

  - [x] 2.2 Capture live Step Functions definition
    - Read `kr-data-pipeline-dev`
    - Identify each state Resource ARN
    - Confirm whether live `VectorStage` calls loader or vector Lambda
    - _Requirements: 2.2, 2.5_

  - [x] 2.3 Capture live IAM and Layer references
    - Read Step Functions execution role policy
    - Read Lambda execution role policy
    - Read existing Lambda layer versions used by pipeline functions
    - _Requirements: 2.3, 2.4_

  - [x] 2.4 Write baseline drift report
    - Path: `docs/reports/kr_lambda_sfn_batch_reset_baseline_YYYYMMDD.md`
    - Include live vs Terraform differences
    - Include timeout evidence and current vector routing risk
    - Include `visitor_statistics` coverage baseline and branch enrichment baseline
    - Stop for user review
    - _Requirements: 2.6, 2.7, 3.1-3.9, 4.1-4.9, 9.5, 9.6_

- [x] 3. Close visitor_statistics and enrichment field loading gates
  - [x] 3.1 Verify visitor_statistics source and live coverage
    - Required Context:
      - `docs/reports/visitor_statistics_gap_check_20260630.md`
      - `docs/specs/kr_20260629_preprocessing_redesign_spec.md`
      - `scripts/backfill_visitor_statistics.py`
      - `src/kr_details_pipeline/visitor_statistics_backfill.py`
    - Confirm DataLab raw contract: `raw/KR/datalab/20260629/visitor_statistics_2025.json`
    - Confirm live `TourKoreaDomainDataV2` has 2,820 `visitor_statistics` rows unless a newer approved count exists
    - Confirm 235 city PKs x 12 months and document the five residual city PKs
    - Confirm `SK=STAT#{YYYYMM}`, `domain_sort_key=STAT#{YYYYMM}`, and no `gsi_sk`
    - _Requirements: 3.1-3.9_

  - [x] 3.2 Run visitor_statistics local verification
    - Command:
      `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m pytest src\kr_details_pipeline\tests\test_visitor_statistics_backfill.py src\kr_details_pipeline\tests\test_load.py src\kr_details_pipeline\tests\test_domain_preprocess.py src\kr_vector_index\tests\test_export.py --basetemp .cache\pytest-tmp -p no:cacheprovider`
    - Confirm `visitor_statistics` remains excluded from vectorization
    - _Requirements: 3.4-3.9_

  - [x] 3.3 Verify enrichment field loading baseline
    - Required Context:
      - `.kiro/specs/enrichment-backfill-vector-rebuild/requirements.md`
      - `.kiro/specs/enrichment-backfill-vector-rebuild/tasks.md`
      - `src/kr_details_pipeline/enrichment_persistence.py`
      - `scripts/backfill_enrichment.py`
    - Record current branch name in the baseline
    - Count `metadata_enrichment`
    - Count `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, and `schema_version`
    - Confirm whether vector smoke test will run in enrichment-complete or non-enrichment-complete mode
    - _Requirements: 4.1-4.9_

  - [x] 3.4 Run enrichment loading local verification
    - Command:
      `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m pytest src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrich_attraction.py src\kr_vector_index\tests --basetemp .cache\pytest-tmp -p no:cacheprovider`
    - Confirm succeeded enrichment can write derived fields
    - Confirm failed/skipped enrichment does not clobber unrelated DynamoDB fields
    - Confirm vector metadata does not include full `metadata_enrichment`
    - _Requirements: 4.3-4.9_

  - [x] 3.5 Stop for user review before Terraform reset work
    - Report visitor statistics count and residual city PKs
    - Report enrichment field counts and whether backfill is still required
    - Do not proceed to Terraform reset if either gate contradicts the approved scope
    - _Requirements: 3.9, 4.8, 4.9_

- [x] 4. Prepare Terraform execution-plane reset
  - [x] 4.1 Refactor Terraform Lambda resources
    - Keep transform/image/loader names unless user approves renaming
    - Use `kr-pipeline-vector` as the explicit planner/worker/aggregator command surface unless user approves separate function names
    - Keep layer/package boundaries explicit; layer strategy does not claim to solve timeout
    - Ensure packages exclude tests and cache files
    - _Requirements: 5.1, 6.1-6.6, 8.1-8.5_

  - [x] 4.2 Refactor Step Functions definition
    - Keep TransformStage Map
    - Keep ImageStage Map
    - Keep LoadStage as loader-only
    - Add or preserve `VisitorStatsCoverageGate`
    - Add or preserve `EnrichmentFieldLoadingGate`
    - Add VectorPlanStage
    - Add VectorBatchStage Map
    - Add VectorAggregateStage
    - Ensure VectorStage no longer calls loader vector-build
    - _Requirements: 3.1-3.9, 4.1-4.9, 7.1-7.10, 8.6, 8.7_

  - [x] 4.3 Refactor IAM policies
    - Allow Step Functions to invoke the new vector planner/worker/aggregator functions
    - Keep least-privilege access to DynamoDB, Bedrock, S3, and S3 Vectors
    - Remove obsolete invoke dependency where safe
    - Removed Lambda execution role `dynamodb:DeleteItem` and `s3:DeleteObject` permissions from Terraform desired state after confirming runtime code does not call delete APIs
    - _Requirements: 2.4, 5.1, 9.3_

  - [x] 4.4 Run static Terraform checks
    - Command:
      `terraform -chdir=infrastructure/terraform fmt -check`
    - Command:
      `terraform -chdir=infrastructure/terraform validate`
    - _Requirements: 9.1_

- [x] 5. Implement vector batch runtime
  - [x] 5.1 Add vector planner behavior
    - Generate deterministic batch descriptors
    - Support small smoke-test limit
    - Exclude `visitor_statistics`
    - Include enrichment baseline mode in plan output
    - Write large batch plans to S3 if Step Functions payload size is at risk
    - Return compact batch references
    - _Requirements: 3.8, 4.8, 7.2, 7.3, 7.10_

  - [x] 5.2 Add vector worker behavior
    - Read one batch descriptor
    - Fetch assigned items only
    - Build chunks
    - Generate Titan embeddings
    - PutVectors in allowed batch size
    - Return compact result and failure details
    - _Requirements: 7.5-7.9_

  - [x] 5.3 Add vector aggregator behavior
    - Aggregate batch results
    - Write final manifest to S3
    - Preserve failed batch ids for retry
    - Mark final status as succeeded, partial, or failed
    - _Requirements: 7.8, 7.9, 9.5-9.9_

  - [x] 5.4 Add tests for vector batch behavior
    - Planner creates deterministic batches
    - Worker bounds item count
    - Worker records retryable failures
    - Aggregator writes compact manifest
    - Loader no longer owns vector-build
    - `visitor_statistics` remains excluded
    - Enrichment metadata allowlist is preserved
    - _Requirements: 3.8, 4.6, 4.7, 7.1-7.10, 8.5_

  - [x] 5.5 Run Python tests
    - Command:
      `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m pytest src\kr_vector_index\tests src\kr_unified_pipeline\tests\test_vector_rebuilder.py --basetemp .cache\pytest-tmp -p no:cacheprovider`
    - Add or adjust focused test paths if new vector batch modules are introduced elsewhere.
    - _Requirements: 9.2_

- [x] 6. Review Terraform plan before apply
  - [x] 6.1 Generate Terraform plan
    - Command:
      `terraform -chdir=infrastructure/terraform plan -out=.cache\terraform\kr-lambda-sfn-batch-reset.tfplan`
    - If `.cache\terraform` does not exist, create it inside workspace.
    - _Requirements: 5.4_

  - [x] 6.2 Inspect protected resource actions
    - Confirm no DynamoDB table delete or recreate
    - Confirm no S3 bucket delete or recreate
    - Confirm no S3 object delete action
    - Confirm no S3 Vector index delete unless separately approved
    - Confirm `visitor_statistics` rows are not removed by reset work
    - Confirm enrichment fields are not wiped by reset work
    - _Requirements: 1.1-1.6, 3.1-3.9, 4.1-4.9, 5.5_

  - [x] 6.3 Inspect execution-plane actions
    - Confirm expected Lambda creates/replaces
    - Confirm expected Layer creates/replaces
    - Confirm expected Step Functions update
    - Confirm expected IAM policy updates
    - Confirm visitor/enrichment gates remain before vector rebuild
    - _Requirements: 3.1-3.9, 4.1-4.9, 5.1-5.6, 6.1-6.6_

  - [x] 6.4 Stop for user approval
    - Report plan summary in Korean
    - Include protected-resource verification
    - Include visitor statistics and enrichment field gate status
    - Include live apply-pending drift: old `VectorStage -> loader vector-build` routing and live delete permissions remain until Terraform apply
    - Write apply approval package at `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
    - Write Task 7 handoff sheet at `docs/specs/TASK7_SUBTASKS.md`
    - Prepare read-only post-apply verifier at `src/kr_vector_index/live_verification.py`
    - Prepare read-only post-apply verifier CLI at `python -m kr_vector_index.live_verification_cli`
    - Do not apply until the user explicitly approves
    - _Requirements: 5.6_

- [ ] 7. Apply and smoke test after approval
  - Start from the next-session handoff package before any apply preflight: `docs/reports/kr_lambda_sfn_batch_reset_next_session_handoff_20260630.md`
  - [ ] 7.1 Apply approved Terraform plan
    - Command:
      `terraform -chdir=infrastructure/terraform apply .cache\terraform\kr-lambda-sfn-batch-reset.tfplan`
    - Capture output and failures
    - _Requirements: 5.1-5.6_

  - [ ] 7.2 Verify live Lambda/SFN wiring
    - Read Lambda configurations after apply
    - Read state machine definition after apply
    - Confirm `VectorBatchStage` Map exists
    - Confirm loader is not called for vector-build
    - Confirm visitor/enrichment gates still precede vector rebuild
    - _Requirements: 3.1-3.9, 4.1-4.9, 8.5-8.7, 9.3_

  - [ ] 7.3 Run vector planner smoke test
    - Use a small limit or one city/batch
    - Confirm batch descriptor output
    - Confirm no full rebuild has started
    - Confirm `visitor_statistics` is excluded
    - Report whether enrichment fields were expected in the sampled batch
    - _Requirements: 3.8, 4.6-4.8, 7.2, 7.10, 9.4_

  - [ ] 7.4 Run vector worker smoke test
    - Execute one or two batches
    - Confirm no timeout
    - Confirm vectors are upserted to the approved target index
    - Confirm failed batch reporting works
    - Stop before full rebuild
    - _Requirements: 7.5-7.10, 9.4_

- [ ] 8. Full vector rebuild after smoke-test approval
  - [ ] 8.1 Request approval for full VectorBatchStage execution
    - Include smoke-test duration, count, failure, and cost-risk evidence
    - Confirm target index again
    - Confirm MaxConcurrency again
    - Reconfirm visitor statistics and enrichment loading gate results
    - _Requirements: 3.1-3.9, 4.1-4.9, 7.4, 7.10_

  - [ ] 8.2 Run full vector batch workflow
    - Start Step Functions execution
    - Monitor failed batches
    - Retry only failed batches where supported
    - _Requirements: 7.3-7.9_

  - [ ] 8.3 Verify full rebuild output
    - Count expected items
    - Count vectors
    - Verify sample query
    - Verify manifest
    - Verify no protected data deletion occurred
    - Verify `visitor_statistics` vector count remains 0
    - Verify enrichment metadata rules when succeeded enrichment exists
    - _Requirements: 1.1-1.6, 3.8, 4.6-4.8, 9.4-9.9_

- [ ] 9. Completion report and review
  - [ ] 9.1 Write Korean completion report
    - Path: `docs/reports/kr_lambda_sfn_batch_reset_completion_YYYYMMDD.md`
    - Follow required evidence template: `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`
    - Include baseline, plan, apply, smoke test, full rebuild status, and remaining risks
    - Include visitor statistics count, residual city PKs, and vector exclusion evidence
    - Include branch name and enrichment field counts
    - Do not mark active goal complete if `visitor_statistics` evidence, branch `investigate/enrichment-field-loading-20260628`, enrichment loading/backfill status, or protected DynamoDB/S3/S3 Vector evidence is missing
    - _Requirements: 9.5-9.9_

  - [ ] 9.2 Review completed task
    - Review Terraform scope
    - Review Lambda responsibility split
    - Review Step Functions resource wiring
    - Review visitor statistics coverage gate
    - Review enrichment field loading gate
    - Review vector batch retry behavior
    - Review security-sensitive IAM changes
    - Stop for user confirmation before any follow-up cleanup
    - _Requirements: 3.1-3.9, 4.1-4.9, 8.1-8.7, 9.1-9.9_

## Stop Conditions

- Stop before any Terraform apply.
- Stop if Terraform plan deletes or recreates protected DynamoDB or S3 resources.
- Stop if live AWS cannot be queried before reset.
- Stop if `visitor_statistics` coverage or key-shape checks contradict the approved baseline.
- Stop if enrichment field loading baseline is missing from the report.
- Stop if Step Functions definition after apply still routes vector build to loader.
- Stop if vector smoke test reaches timeout.
- Stop if three consecutive batch failures occur.
- Stop before deleting any existing S3 Vector index.
- Stop before full vector rebuild unless smoke test has passed and the user approves.
