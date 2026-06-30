# Implementation Plan: enrichment-backfill-vector-rebuild

## Overview

이 계획은 최신 취득 데이터가 반영된 `TourKoreaDomainDataV2`를 기준으로 enrichment 결과를 DynamoDB에 저장하고, 같은 bucket `lovv-vector-dev` 안에 신규 `kr-tour-domain-v2` index를 생성해 적재하기 위한 작업을 작은 단위로 나눈다.

작업 모드는 Sequential Mode를 사용한다. DynamoDB 쓰기, Bedrock 호출, S3 Vector 신규 index 생성 및 라우팅 전환 가능성이 있으므로 각 Task 완료 후 검증과 사용자 확인이 필요하다.

## Tasks

- [ ] 1. Spec approval and execution boundary confirmation
  - [ ] 1.1 Review this spec with the user
    - Confirm default Source_Table is `TourKoreaDomainDataV2`
    - Confirm Source_Table reflects the latest acquired KR dataset before writes
    - Confirm `TourKoreaDomainData` V1 remains untouched unless separately approved
    - Confirm target vector index is `lovv-vector-dev/kr-tour-domain-v2`
    - Confirm first real backfill limit
    - Confirm whether AgentCore V1 index is in scope
    - _Requirements: 1.1, 1.2, 1.3, 4.2, 4.3, 4.12_

  - [ ] 1.2 Capture current live baseline
    - Count V2 attraction items
    - Count existing `metadata_enrichment`
    - Count each Enrichment_Derived_Field
    - Confirm latest acquisition source prefix/date and V2 item counts
    - Count current vectors and enrichment metadata in `kr-tour-domain-v1`
    - Confirm whether `kr-tour-domain-v2` already exists
    - Save evidence in `docs/reports/`
    - _Requirements: 1.2, 1.4, 4.5, 5.1, 5.2_

- [ ] 2. Implement enrichment persistence adapter
  - [ ] 2.1 Add failing tests for `EnrichmentResult` to DynamoDB UpdateItem mapping
    - Success writes top-level `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `schema_version="2"`, and `metadata_enrichment`
    - Failed result writes only `metadata_enrichment`
    - Skipped result does not clear existing derived fields
    - Missing `PK` or `SK` is rejected before write
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8_

  - [ ] 2.2 Implement `src/kr_details_pipeline/enrichment_persistence.py`
    - Add `update_attraction_enrichment()`
    - Use DynamoDB `UpdateItem`
    - Preserve source and deterministic fields
    - Serialize DynamoDB values through boto3-compatible types
    - _Requirements: 2.1, 2.6, 2.7_

  - [ ] 2.3 Run local verification
    - Command:
      `UV_CACHE_DIR=.cache/uv uv run python -m pytest src/kr_details_pipeline/tests/test_enrichment_persistence.py src/kr_details_pipeline/tests/test_enrich_attraction.py -q --basetemp .cache/pytest-tmp -p no:cacheprovider`
    - _Requirements: 2.1-2.8_

- [ ] 3. Implement bounded backfill runner
  - [ ] 3.1 Add backfill runner tests
    - Dry-run does not call Bedrock
    - Dry-run does not write DynamoDB
    - `--limit` bounds candidate count
    - `--city-pk` filters scope
    - Existing succeeded same hash is skipped
    - Three consecutive write/model failures stop the run
    - _Requirements: 3.1, 3.2, 3.4, 3.7, 3.8_

  - [ ] 3.2 Implement `scripts/backfill_enrichment.py`
    - Read from `TourKoreaDomainDataV2` by default
    - Include source dataset date or prefix in effective parameter output
    - Process only attraction items
    - Support `--dry-run`, `--limit`, `--city-pk`, `--resume-after`, `--profile`, `--region`, `--table-name`, `--model-id`
    - Call `enrich_attraction()` only during real run
    - Persist through `update_attraction_enrichment()`
    - Print JSON summary
    - _Requirements: 1.1, 1.4, 3.1-3.8_

  - [ ] 3.3 Run local verification
    - Command:
      `UV_CACHE_DIR=.cache/uv uv run python -m pytest src/kr_details_pipeline/tests scripts -q --basetemp .cache/pytest-tmp -p no:cacheprovider`
    - If script tests are not collected under `scripts`, add a focused test path and document it.
    - _Requirements: 3.1-3.8_

- [ ] 4. Execute V2 backfill in guarded stages
  - [ ] 4.1 Run V2 dry-run
    - Command shape:
      `UV_CACHE_DIR=.cache/uv uv run python scripts/backfill_enrichment.py --profile skn26_final --region us-east-1 --table-name TourKoreaDomainDataV2 --limit 50 --dry-run`
    - Save summary to report
    - Stop for user review before real writes
    - _Requirements: 1.3, 1.4, 3.2, 5.4_

  - [ ] 4.2 Run limited V2 real backfill after approval
    - Use the user-approved limit
    - Verify post-run DynamoDB field counts
    - Verify no unexpected writes to V1
    - Save summary to report
    - Stop for user review before full run
    - _Requirements: 2.1-2.8, 3.5, 3.6, 5.2_

  - [ ] 4.3 Run full V2 backfill after approval
    - Resume from cursor if needed
    - Record success/failure/skipped counts
    - Verify non-zero succeeded enrichment count
    - Save failed item list and retry plan
    - _Requirements: 3.4, 3.5, 3.6, 5.5_

- [ ] 5. Implement same-bucket Vector V2 build safety
  - [ ] 5.1 Add V2 build planning tests
    - Target index existence is detected before writes
    - Missing `kr-tour-domain-v2` plans a new index creation in `lovv-vector-dev`
    - Existing `kr-tour-domain-v2` stops unless an explicit target recreation or alternate-name decision is provided
    - `kr-tour-domain-v1` is never deleted, recreated, or overwritten
    - Upsert-only writes to an existing target are not reported as a clean V2 build unless target state was approved
    - _Requirements: 4.3, 4.4, 4.5_

  - [ ] 5.2 Implement V2 index build path
    - Add dry-run that lists previous vector count, target index state, desired vector count, and expected write count
    - Create or target `lovv-vector-dev/kr-tour-domain-v2`
    - Preserve index data type, dimension, distance metric, and metadata configuration
    - Verify IAM/resource ARN coverage for the V2 index before routing
    - Stop if V2 index creation or allowed target recreation permissions are missing
    - _Requirements: 4.1-4.6, 4.10_

  - [ ] 5.3 Run local verification
    - Command:
      `UV_CACHE_DIR=.cache/uv uv run python -m pytest src/kr_unified_pipeline/tests/test_vector_rebuilder.py src/kr_vector_index/tests -q --basetemp .cache/pytest-tmp -p no:cacheprovider`
    - _Requirements: 4.1-4.9_

- [ ] 6. Execute same-bucket Vector V2 build after approval
  - [ ] 6.1 Run Vector V2 build dry-run
    - Target: `lovv-vector-dev/kr-tour-domain-v2`
    - Previous rollback index: `lovv-vector-dev/kr-tour-domain-v1`
    - Source: `TourKoreaDomainDataV2`
    - Report latest source evidence, previous count, target existence, desired count, and expected write count
    - Stop for user approval before creating or recreating a target index
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ] 6.2 Create/build V2 index
    - Create `kr-tour-domain-v2` in `lovv-vector-dev` if missing
    - Rebuild vectors from latest V2 source into `kr-tour-domain-v2`
    - Keep `kr-tour-domain-v1` unchanged for rollback
    - Do not rebuild AgentCore V1 unless separately approved
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 4.12_

  - [ ] 6.3 Verify vector metadata
    - Count rebuilt vectors
    - Count attraction vectors with each enrichment field
    - Verify `metadata_enrichment` is absent from vector metadata
    - Verify 2KB metadata budget remains enforced
    - _Requirements: 4.7, 4.8, 4.9, 5.2_

  - [ ] 6.4 Approve and execute routing switch
    - Verify search/query checks against `kr-tour-domain-v2`
    - Confirm IAM/resource policies allow the runtime to query V2
    - Switch routing only after user approval
    - Keep rollback path to `kr-tour-domain-v1`
    - _Requirements: 4.10, 4.11_

- [ ] 7. Final report and review
  - [ ] 7.1 Write Korean completion report
    - Path: `docs/reports/enrichment_backfill_vector_rebuild_YYYYMMDD.md`
    - Include commands, counts, samples, failures, and remaining risks
    - State whether `S3 Vector V2 적재 완료` and routing switch actually occurred
    - _Requirements: 5.1-5.6_

  - [ ] 7.2 Review completed work
    - Review changed code against this spec
    - Review security-sensitive paths: DynamoDB writes, Bedrock calls, S3 Vector index creation, and routing configuration
    - Run required local tests
    - Stop for user confirmation before any next top-level Task
    - _Requirements: 5.1-5.6_

## Stop Conditions

- Stop after each top-level Task and request user review or approval.
- Stop after three consecutive Bedrock, DynamoDB, or S3 Vector failures.
- Stop before V1 writes unless the user explicitly approves V1 scope.
- Stop before deleting/recreating an existing V2 target unless the user explicitly approves the exact target index.
- Stop if any step would delete, recreate, or overwrite `kr-tour-domain-v1`.
- Stop if live counts contradict the expected Source_Table or vector index.
