# Requirements Document

## Introduction

본 문서는 KR 데이터 파이프라인에서 이미 구현된 Bedrock 관광지 enrichment 결과를 최신 취득 데이터 기준 DynamoDB에 안전하게 적재하고, 그 결과를 반영하여 같은 S3 Vector bucket 안에 V2 index를 신규 구축하는 운영 보완 작업의 요구사항을 정의한다.

현재 확인된 상태는 다음과 같다.

- `TourKoreaDomainData` 관광지 5,652건, `TourKoreaDomainDataV2` 관광지 6,335건 모두 `metadata_enrichment` 및 top-level enrichment 필드가 0건이다.
- `lovv-vector-dev/kr-tour-domain-v1` 전체 vector 7,073건 중 enrichment 필드(`indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `schema_version`)는 0건이다.
- `lovv-agentcore-v1-vector/kr-agentcore-v1` 전체 vector 2,125건도 동일하게 enrichment 필드가 0건이다.
- 현행 vector rebuild 구현은 기존 vector를 삭제하지 않고 `put_vectors`로 upsert만 수행하므로, stale vector가 남을 수 있다.
- 현재 취득/전처리 근거는 `docs/reports/kr_data_acquisition_report_20260628.md`와 `docs/reports/kr_nationwide_pipeline_report_20260628.md`이며, 관광지/축제는 `raw/KR/details/20260625/`, 방문자 통계는 2026-06-28 취득, 운영 적재 테이블은 `TourKoreaDomainDataV2`다.
- 기존 `lovv-vector-dev/kr-tour-domain-v1`은 운영 롤백용으로 보존하고, 재색인은 같은 bucket의 신규 target index `kr-tour-domain-v2`에 적재한 뒤 검증 통과 시 라우팅을 전환한다.

따라서 이 작업은 단순 vector 재생성이 아니라 다음 순서로 진행되어야 한다.

1. 최신 취득 데이터가 반영된 DynamoDB V2 기준 enrichment persistence/backfill 구현 및 제한 실행
2. DynamoDB 적재 결과 검증
3. 같은 S3 Vector bucket의 신규 V2 index 생성 및 적재
4. V2 vector metadata 검증, 라우팅 전환 판단, 운영 보고

## Glossary

- **Enrichment_Backfill**: 기존 DynamoDB attraction item을 읽어 Bedrock enrichment를 실행하고 결과를 다시 DynamoDB에 저장하는 배치 작업
- **Persistence_Adapter**: `EnrichmentResult`를 DynamoDB `UpdateItem` 요청으로 변환하는 저장 계층
- **Latest_Acquired_Dataset**: 실행 시점에 가장 최근 취득 및 전처리 완료가 확인된 KR 원천 데이터셋. 현재 근거는 관광지/축제 `raw/KR/details/20260625/`, 방문자 통계 2026-06-28 취득, `TourKoreaDomainDataV2` 적재 결과다.
- **Vector_V2_Build**: 기존 V1 index를 삭제하지 않고 같은 bucket의 신규 V2 index에 DynamoDB 원천에서 vector를 다시 쓰는 작업
- **Source_Table**: enrichment 및 vector V2 build의 기준 DynamoDB 테이블. 기본값은 최신 취득 데이터가 적재된 `TourKoreaDomainDataV2`
- **Vector_Bucket**: S3 Vector bucket. 기본값은 기존 운영 bucket `lovv-vector-dev`
- **Target_Vector_Index**: 신규 적재 대상 index. 기본값은 `kr-tour-domain-v2`
- **Previous_Vector_Index**: 기존 운영/롤백 index. 기본값은 `kr-tour-domain-v1`
- **Legacy_Table**: 기존 `TourKoreaDomainData` 테이블. 명시 승인 없이는 backfill 대상이 아니다
- **Runtime_Evidence**: live AWS read-only scan, dry-run output, limited execution summary, vector metadata count처럼 실제 실행으로 얻은 증거
- **Enrichment_Derived_Fields**: `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, top-level `schema_version`

## Requirements

### Requirement 1: 운영 기준 테이블 및 범위 확정

**User Story:** As a 데이터 엔지니어, I want enrichment backfill의 기준 테이블과 범위를 명확히 확정하고 싶다, so that legacy 데이터나 잘못된 테이블을 실수로 변경하지 않는다.

#### Acceptance Criteria

1. THE Backfill_Workflow SHALL use `TourKoreaDomainDataV2` as the default Source_Table.
2. THE Backfill_Workflow SHALL confirm that Source_Table reflects the Latest_Acquired_Dataset before any write operation.
3. THE Backfill_Workflow SHALL NOT update `TourKoreaDomainData` unless the user explicitly approves V1 backfill in a separate confirmation.
4. BEFORE any write operation, THE Backfill_Workflow SHALL run a read-only count check for attraction item count, existing `metadata_enrichment` count, and each Enrichment_Derived_Field count.
5. BEFORE any write operation, THE Backfill_Workflow SHALL print or persist the effective parameters: table name, region, profile, model id, prompt version, source dataset date or prefix, limit, city filter, dry-run mode, and resume cursor.
6. IF the Source_Table has zero attraction items, THEN THE Backfill_Workflow SHALL stop without invoking Bedrock or writing DynamoDB.
7. IF the effective table name differs from `TourKoreaDomainDataV2`, THEN THE Backfill_Workflow SHALL require explicit user confirmation before continuing.

### Requirement 2: Enrichment 결과 DynamoDB 저장

**User Story:** As a 검색 서비스, I want Bedrock enrichment 결과가 DynamoDB attraction item에 저장되길 원한다, so that vector rebuild가 감성·경험·동행 metadata를 복사할 수 있다.

#### Acceptance Criteria

1. WHEN `enrich_attraction()` returns `status="succeeded"`, THE Persistence_Adapter SHALL update only the target item identified by `PK` and `SK`.
2. WHEN the result is succeeded, THE Persistence_Adapter SHALL write top-level `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, and `schema_version="2"`.
3. WHEN the result is succeeded, THE Persistence_Adapter SHALL write `metadata_enrichment.status="succeeded"`, `model_id`, `prompt_version`, `schema_version`, `generated_at`, and `input_hash`.
4. WHEN `enrich_attraction()` returns `status="failed"`, THE Persistence_Adapter SHALL update only `metadata_enrichment` and SHALL NOT write or delete Enrichment_Derived_Fields.
5. WHEN `enrich_attraction()` returns `status="skipped"`, THE Persistence_Adapter SHALL preserve existing successful derived fields if they exist and SHALL NOT clear them.
6. THE Persistence_Adapter SHALL use DynamoDB `UpdateItem`, not full `PutItem`, to avoid clobbering unrelated item fields.
7. THE Persistence_Adapter SHALL NOT overwrite `title`, `description`, `theme`, `theme_tags`, `experience_guide`, `opening_hours`, `closed_days`, `parking`, `address`, `entity_type`, `content_id`, `PK`, `SK`, `source_key`, `raw_s3_uri`, `classification_source`, or `classification_mapping_version`.
8. IF a target item is missing `PK` or `SK`, THEN THE Backfill_Workflow SHALL record the item as failed and SHALL NOT attempt a write.

### Requirement 3: Backfill 실행 안전장치

**User Story:** As an 운영 엔지니어, I want backfill을 작게 검증한 뒤 점진적으로 확대하고 싶다, so that Bedrock 비용, throttling, 부분 실패, 중복 처리 위험을 줄일 수 있다.

#### Acceptance Criteria

1. THE Backfill_Runner SHALL support `--dry-run`, `--limit`, `--city-pk`, `--resume-after`, `--profile`, `--region`, `--table-name`, and `--model-id`.
2. WHEN `--dry-run` is set, THE Backfill_Runner SHALL read candidate items and compute planned actions but SHALL NOT call Bedrock and SHALL NOT write DynamoDB unless a separate `--dry-run-with-model` option is explicitly introduced and approved.
3. THE Backfill_Runner SHALL process only `entity_type="attraction"` items.
4. THE Backfill_Runner SHALL skip items where `metadata_enrichment.status="succeeded"` and `input_hash`, `prompt_version`, and `model_id` match the current enrichment input.
5. THE Backfill_Runner SHALL continue processing after an individual item failure and SHALL include failed item ids and error categories in the summary.
6. THE Backfill_Runner SHALL emit a machine-readable summary with total candidates, processed, succeeded, skipped, failed, unchanged, and written counts.
7. THE Backfill_Runner SHALL support bounded first execution with `--limit` before any full-table run.
8. IF three consecutive Bedrock or DynamoDB write failures occur, THEN THE Backfill_Runner SHALL stop and report the current cursor for resume.

### Requirement 4: 같은 bucket의 Vector V2 index 구축

**User Story:** As a 검색 서비스, I want 같은 S3 Vector bucket 안에 V2 index를 새로 적재하고 싶다, so that V1을 롤백용으로 보존하면서 DynamoDB V2의 최신 enrichment metadata를 검증할 수 있다.

#### Acceptance Criteria

1. THE Vector_Rebuild SHALL run only after DynamoDB V2 enrichment field counts are verified.
2. THE Vector_Rebuild SHALL use `TourKoreaDomainDataV2` and `EntityTypeDomainIndex` as the default source path for `lovv-vector-dev/kr-tour-domain-v2`.
3. THE Vector_Rebuild SHALL create or target a new index in the same Vector_Bucket `lovv-vector-dev`, not a new bucket.
4. THE Vector_Rebuild SHALL NOT delete, recreate, or overwrite Previous_Vector_Index `lovv-vector-dev/kr-tour-domain-v1` during the V2 build.
5. IF Target_Vector_Index `kr-tour-domain-v2` already exists, THEN THE Vector_Rebuild SHALL stop and require explicit user confirmation before deleting/recreating that V2 target or choosing a new target name.
6. THE Vector_Rebuild SHALL preserve the existing index contract: float32, 1024 dimensions, cosine distance, and non-filterable metadata keys `raw_s3_uri`, `ddb_pk`, `ddb_sk`, `embedding_model`.
7. THE Vector_Rebuild SHALL verify that rebuilt attraction vectors include enrichment fields for items where `metadata_enrichment.status="succeeded"`.
8. THE Vector_Rebuild SHALL verify that vector metadata never includes the full `metadata_enrichment` object.
9. THE Vector_Rebuild SHALL verify that filterable metadata remains within the 2KB budget.
10. THE Vector_Rebuild SHALL verify IAM/resource configuration for the new V2 index before routing traffic to it.
11. THE Workflow SHALL switch search routing from `kr-tour-domain-v1` to `kr-tour-domain-v2` only after vector count, sample metadata, and query checks pass.
12. THE AgentCore V1 index `lovv-agentcore-v1-vector/kr-agentcore-v1` SHALL be rebuilt only after the user confirms it still needs the same enrichment metadata.

### Requirement 5: 검증 및 보고

**User Story:** As a teammate, I want the result to include concrete evidence, so that I can trust whether enrichment and vector rebuild actually completed.

#### Acceptance Criteria

1. THE Workflow SHALL produce a Korean report under `docs/reports/`.
2. THE report SHALL include pre-run DynamoDB counts, post-backfill DynamoDB counts, pre-rebuild vector counts, post-rebuild vector counts, and sample metadata evidence.
3. THE report SHALL state whether `S3 Vector 재생성 완료` was actually performed or whether the work stopped before destructive execution.
4. THE report SHALL include exact commands or Lambda payloads used for dry-run, limited run, full backfill, and vector rebuild.
5. THE report SHALL list failed items and retry recommendations when any failure occurs.
6. THE report SHALL avoid claiming enrichment/vector completion unless live AWS evidence confirms it.

## Non-Goals

- This spec does not redesign the existing Bedrock prompt taxonomy.
- This spec does not add user-specific theme weighting or recommendation scoring.
- This spec does not backfill `TourKoreaDomainData` V1 unless separately approved.
- This spec does not change restaurant collection or restaurant vector behavior.
- This spec does not change the S3 Vector embedding model or vector dimensionality.

## Success Criteria

- `TourKoreaDomainDataV2` reflects the latest acquired KR dataset before backfill starts.
- `TourKoreaDomainDataV2` has non-zero `metadata_enrichment.status="succeeded"` attraction items after bounded and approved backfill.
- The same succeeded items have top-level `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, and `schema_version`.
- `lovv-vector-dev/kr-tour-domain-v2` is newly built from V2 in the same bucket while `kr-tour-domain-v1` remains available for rollback.
- Attraction vectors sourced from succeeded enrichment items include the enrichment metadata fields.
- Full `metadata_enrichment` is not present in vector metadata.
- A Korean execution report captures evidence and remaining risks.

## Open Questions

1. Should `TourKoreaDomainData` V1 remain untouched, or does AgentCore V1 require V1 enrichment as well?
2. Is `kr-tour-domain-v2` the approved final Target_Vector_Index name, or should a dated/indexed name be used for this run?
3. Which runtime configuration or agent route owns the final switch from `kr-tour-domain-v1` to `kr-tour-domain-v2`?
4. What is the approved first bounded backfill size: 10, 50, 100, or a specific city?
