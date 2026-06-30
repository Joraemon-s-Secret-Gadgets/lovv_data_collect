# Requirements Document

## Introduction

본 문서는 KR 데이터 파이프라인의 Lambda 및 Step Functions 실행 계층을 통제된 방식으로 내리고, Lambda Layer와 Step Functions Map/batch worker 구조로 재구성하기 위한 요구사항을 정의한다.

이번 작업의 핵심 배경은 단순 timeout 수정이 아니다. 기존 구조는 `kr-pipeline-transform`, `kr-pipeline-image`, `kr-pipeline-loader`, `kr-pipeline-vector`, Step Functions `VectorStage`가 부분적으로 수정되면서 live AWS와 Terraform 코드 사이에 drift가 생겼고, 특히 `VectorStage`가 전용 vector Lambda가 아니라 loader Lambda를 호출하는 누락이 반복되었다. 따라서 이번 작업은 Lambda 실행 계층을 부분 보수하지 않고, DynamoDB와 S3 데이터 계층을 보존한 상태에서 Lambda/SFN 계층을 하나의 배포 단위로 재정리한다.

추가로 이번 reset은 계속 누락되었던 `visitor_statistics` 보완과 현재 브랜치 `investigate/enrichment-field-loading-20260628`의 의도인 enrichment field loading/backfill 보존을 필수 범위로 포함한다. 실행 계층을 내리고 다시 올리는 과정에서 방문자 통계 검증과 enrichment field 적재 검증이 빠지면 같은 누락이 반복되므로, 두 항목은 vector batch reset의 선행 gate와 최종 보고 항목으로 고정한다.

현재 확인된 기준 사실은 다음과 같다.

- `kr-pipeline-loader`의 vector-build 경로는 live CloudWatch에서 900초 timeout을 기록했다.
- local Terraform은 `VectorStage`가 `kr-pipeline-vector`를 호출하도록 수정되어 있으나, live Step Functions는 아직 `kr-pipeline-loader`를 호출하고 있다.
- `kr-pipeline-vector`도 현재 구현상 full vector rebuild를 단일 Lambda 실행에서 순차 embedding하는 구조라 7천 건 이상 재색인에 대해 timeout 위험이 남아 있다.
- Lambda Layer는 dependency packaging에는 유용하지만 timeout 자체를 해소하지 않는다.
- timeout 해소의 핵심은 vector rebuild를 Step Functions Map 또는 batch worker 구조로 분할하는 것이다.
- `visitor_statistics`는 2026-06-30 보완 후 live `TourKoreaDomainDataV2`에 2,820건, 235개 도시 x 12개월로 적재되어야 하며, 잔여 5개 legacy/obsolete city PK 60건은 별도 의사결정 대상으로 남는다.
- `visitor_statistics`는 DynamoDB에는 보존하지만 S3 Vector rebuild 대상에서는 제외한다.
- enrichment field loading 범위는 `metadata_enrichment`, `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `schema_version` 적재와 vector metadata 반영 검증을 포함한다.

## Assumptions

1. DynamoDB 테이블은 삭제하지 않는다.
2. S3 data bucket, image bucket, vector bucket, 기존 raw/processed 산출물은 삭제하지 않는다.
3. 기존 S3 Vector index는 명시 승인 전까지 삭제하지 않는다.
4. Lambda 및 Step Functions 계층은 Terraform으로 관리한다.
5. AWS Console 또는 CLI를 통한 수동 삭제는 emergency rollback을 제외하고 금지한다.
6. 첫 구현은 `dev` 환경, `us-east-1`, 계정 `925273580929` 기준으로 검증한다.
7. `visitor_statistics` 보완 기준은 `raw/KR/datalab/20260629/visitor_statistics_2025.json`, `data/KR/visitor_statistics_2025.json`, live `TourKoreaDomainDataV2` 검증 결과를 기준으로 한다.
8. 현재 브랜치 `investigate/enrichment-field-loading-20260628`의 enrichment loading/backfill 의도는 reset 범위에서 제외하지 않는다.
9. full vector rebuild는 visitor statistics coverage와 enrichment field loading baseline이 확인되기 전에는 실행하지 않는다.

## Glossary

- **Runtime_Reset**: DynamoDB/S3 보존을 전제로 Lambda, Lambda Layer, Step Functions, 관련 IAM policy를 Terraform 기준으로 재구성하는 작업.
- **Protected_Data_Plane**: 삭제하거나 초기화하지 않는 데이터 계층. DynamoDB tables, S3 buckets, S3 object prefixes, S3 Vector buckets/indexes를 포함한다.
- **Execution_Plane**: Lambda functions, Lambda layers, Step Functions state machine, Lambda/SFN IAM role and policy, CloudWatch log groups를 포함하는 실행 계층.
- **Vector_Planner**: DynamoDB 또는 S3 manifest를 기준으로 vector batch 목록을 생성하는 Lambda 또는 command.
- **Vector_Worker**: 하나의 batch를 받아 Titan embedding과 S3 Vectors PutVectors를 수행하는 Lambda.
- **Vector_Aggregator**: batch 결과를 집계하고 manifest를 S3에 기록하는 Lambda 또는 Step Functions state.
- **Live_Drift**: Terraform 코드의 desired state와 AWS live resource configuration이 다르게 된 상태.
- **Approval_Gate**: 파괴적 변경 또는 비용 발생 작업 전에 사용자 승인을 요구하는 중단 지점.
- **Visitor_Statistics_Coverage**: `TourKoreaDomainDataV2`에서 `entity_type="visitor_statistics"` item이 city PK별 2025년 12개월 `STAT#{YYYYMM}` row로 존재하고, `domain_sort_key`와 GSI 오염 여부가 검증된 상태.
- **Enrichment_Field_Loading**: attraction item에 `metadata_enrichment`와 top-level enrichment derived fields를 DynamoDB에 적재하고, vector metadata에는 허용된 derived fields만 반영하는 작업.
- **Enrichment_Derived_Fields**: `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `schema_version`.

## Requirements

### Requirement 1: 데이터 계층 보존

**User Story:** As a 데이터 파이프라인 운영자, I want DynamoDB와 S3 데이터 자산을 보존한 채 실행 계층만 재구성하고 싶다, so that 기존 취득/전처리/이미지/vector 데이터가 손실되지 않는다.

#### Acceptance Criteria

1. THE Runtime_Reset SHALL NOT delete or recreate DynamoDB tables.
2. THE Runtime_Reset SHALL NOT delete S3 buckets.
3. THE Runtime_Reset SHALL NOT delete raw, processed, review, failed, quality, image, or manifest S3 objects.
4. THE Runtime_Reset SHALL NOT delete existing S3 Vector indexes unless a separate explicit approval names the exact vector bucket and index.
5. BEFORE any Terraform apply, THE plan review SHALL show no delete action for protected DynamoDB tables or S3 buckets.
6. IF Terraform plans to delete any Protected_Data_Plane resource, THEN the workflow SHALL stop before apply.

### Requirement 2: live drift와 현재 실행 계층 백업

**User Story:** As an 운영자, I want 현재 live Lambda/SFN 설정을 백업하고 drift를 명확히 확인하고 싶다, so that 재구성 중 누락된 연결이나 잘못된 대상 호출을 반복하지 않는다.

#### Acceptance Criteria

1. THE Workflow SHALL capture live configuration for all KR pipeline Lambda functions.
2. THE Workflow SHALL capture live Step Functions definition for `kr-data-pipeline-dev`.
3. THE Workflow SHALL capture live Lambda layer attachments.
4. THE Workflow SHALL capture IAM policies that allow Step Functions to invoke Lambda functions.
5. THE Workflow SHALL compare live `VectorStage` resource with local Terraform `VectorStage` resource.
6. THE Workflow SHALL persist the drift analysis in a repo-local report before destructive apply.
7. IF live AWS cannot be queried, THEN the workflow SHALL stop before destructive changes.

### Requirement 3: visitor_statistics coverage 보존 및 누락 보완 gate

**User Story:** As a 데이터 파이프라인 운영자, I want Lambda/SFN reset 전후로 방문자 통계 적재 상태를 명확히 검증하고 싶다, so that 계속 누락되던 DataLab 방문자 통계가 다시 빠지지 않는다.

#### Acceptance Criteria

1. BEFORE Terraform apply or full vector rebuild, THE Workflow SHALL verify live `TourKoreaDomainDataV2` `visitor_statistics` count.
2. THE Workflow SHALL verify that the expected completed coverage is 2,820 rows for 235 city PKs x 12 months, unless the user approves a different source-of-truth count.
3. THE Workflow SHALL document the residual five legacy/obsolete city PKs: `CITY#BUKJEJU`, `CITY#CHEONGWON-GUN`, `CITY#JINHAE`, `CITY#MASAN`, and `CITY#NAMJEJU`.
4. THE Workflow SHALL verify that each loaded `visitor_statistics` row uses `SK=STAT#{YYYYMM}`.
5. THE Workflow SHALL verify that each loaded `visitor_statistics` row uses `domain_sort_key=STAT#{YYYYMM}`.
6. THE Workflow SHALL verify that `visitor_statistics` rows do not carry `gsi_sk` and do not enter `FestivalMonthIndex`.
7. THE Workflow SHALL preserve the DataLab raw contract `raw/KR/datalab/20260629/visitor_statistics_2025.json`.
8. THE Workflow SHALL keep `visitor_statistics` excluded from vectorization.
9. IF `visitor_statistics` count, key shape, or vector exclusion contradicts these criteria, THEN the workflow SHALL stop before full reset apply or vector rebuild.

### Requirement 4: 현재 브랜치 enrichment field loading 의도 보존

**User Story:** As a 검색/추천 데이터 운영자, I want 현재 브랜치의 enrichment field loading 보완 의도가 reset 중에도 유지되길 원한다, so that Lambda/SFN 재구성 후 vector metadata가 다시 빈 enrichment 상태로 돌아가지 않는다.

#### Acceptance Criteria

1. THE Workflow SHALL record the source branch name `investigate/enrichment-field-loading-20260628` in baseline and completion reports.
2. BEFORE full vector rebuild, THE Workflow SHALL verify DynamoDB V2 counts for `metadata_enrichment` and each Enrichment_Derived_Field.
3. THE Workflow SHALL preserve the enrichment persistence/backfill scope represented by `src/kr_details_pipeline/enrichment_persistence.py` and `scripts/backfill_enrichment.py`.
4. THE Workflow SHALL verify that succeeded enrichment writes top-level `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, and `schema_version`.
5. THE Workflow SHALL verify that failed or skipped enrichment does not clobber unrelated DynamoDB fields.
6. THE Vector_Workflow SHALL include enrichment derived fields in vector metadata only when `metadata_enrichment.status="succeeded"`.
7. THE Vector_Workflow SHALL NOT include the full `metadata_enrichment` object in vector metadata.
8. IF enrichment baseline counts are zero or unknown, THEN the workflow SHALL report that vector rebuild cannot be claimed as enrichment-complete.
9. IF the reset plan drops enrichment field loading/backfill tests or scripts, THEN the workflow SHALL stop before apply.

### Requirement 5: Terraform-managed reset

**User Story:** As an 인프라 작업자, I want Lambda/SFN 계층을 Terraform으로 내리고 다시 올리고 싶다, so that Terraform state와 live AWS가 더 이상 어긋나지 않는다.

#### Acceptance Criteria

1. THE Runtime_Reset SHALL use Terraform changes, import, moved blocks, taint/replace, or planned resource replacement rather than manual console deletion.
2. THE Runtime_Reset SHALL NOT run `aws lambda delete-function` or console deletion unless explicitly approved as an emergency recovery action.
3. THE Runtime_Reset SHALL preserve or intentionally recreate CloudWatch log groups according to the approved plan.
4. THE Runtime_Reset SHALL produce a `terraform plan` artifact before apply.
5. THE Terraform plan SHALL be reviewed for protected data deletion before apply.
6. THE Workflow SHALL stop for user approval before any `terraform apply`.

### Requirement 6: Lambda Layer packaging

**User Story:** As a 배포 관리자, I want 공통 dependency와 실행 코드를 명확히 분리하고 싶다, so that Lambda packaging 누락과 중복 dependency drift를 줄일 수 있다.

#### Acceptance Criteria

1. THE new Lambda packaging SHALL define which dependencies belong in layers and which source code remains in function ZIP packages.
2. THE Layer strategy SHALL include requests/http dependencies only where needed.
3. THE Layer strategy SHALL NOT claim to solve Lambda timeout.
4. THE Layer artifacts SHALL be built reproducibly from repository scripts.
5. THE Lambda functions SHALL attach only required layers.
6. THE package size and layer size SHALL remain within AWS Lambda ZIP and layer limits.

### Requirement 7: Step Functions Map 기반 vector 분할

**User Story:** As a 검색 인덱스 운영자, I want vector rebuild를 batch 단위로 쪼개고 싶다, so that 900초 Lambda timeout에 걸리지 않고 실패 batch만 재시도할 수 있다.

#### Acceptance Criteria

1. THE new VectorStage SHALL NOT run full rebuild as a single Lambda invocation.
2. THE new VectorStage SHALL create a batch plan before embedding starts.
3. THE new VectorStage SHALL execute vector batches through Step Functions Map.
4. THE Vector Map SHALL use bounded MaxConcurrency.
5. THE Vector_Worker SHALL process a bounded number of chunks per invocation.
6. THE Vector_Worker SHALL call Titan embedding and S3 Vectors PutVectors only for its assigned batch.
7. THE Vector_Worker SHALL return item counts, vector counts, failure counts, and retryable error categories.
8. THE Vector_Aggregator SHALL write a final manifest to S3.
9. IF any batch fails, THEN the workflow SHALL preserve successful batch results and report failed batch ids for retry.
10. THE Workflow SHALL support a small test run before full vector rebuild.

### Requirement 8: 책임 분리

**User Story:** As a 유지보수자, I want Transform, Image, Load, Vector 책임을 명확히 분리하고 싶다, so that 한 Lambda에 기능을 덧붙이다가 Step Functions 연결을 누락하는 일이 줄어든다.

#### Acceptance Criteria

1. `kr-pipeline-transform` SHALL own raw detail preprocessing only.
2. `kr-pipeline-image` SHALL own image download/upload, review image manifest, and image report work.
3. `kr-pipeline-loader` SHALL own processed `passed/` data to DynamoDB load only.
4. Vector planner/worker/aggregator SHALL own DynamoDB/S3-to-S3-Vector rebuild only.
5. `kr-pipeline-loader` SHALL NOT own full vector-build after reset.
6. Step Functions SHALL call the Lambda that owns each responsibility.
7. The final Step Functions definition SHALL include no stale call from `VectorStage` to loader vector-build.

### Requirement 9: verification and reporting

**User Story:** As a 팀원, I want reset 결과를 evidence로 확인하고 싶다, so that Lambda/SFN 누락이 재발하지 않았는지 검증할 수 있다.

#### Acceptance Criteria

1. THE Workflow SHALL run Terraform validation before plan.
2. THE Workflow SHALL run focused Python tests for changed vector planner/worker code.
3. THE Workflow SHALL run a Step Functions definition inspection that confirms stage resources.
4. THE Workflow SHALL run a limited vector batch smoke test before full rebuild.
5. THE Workflow SHALL produce a Korean report under `docs/reports/`.
6. THE report SHALL include live-before, plan, apply, smoke-test, and remaining-risk evidence.
7. THE report SHALL clearly state whether full vector rebuild was executed or only planned.
8. THE report SHALL include `visitor_statistics` live count, city coverage, residual city PKs, key-shape checks, and vector exclusion evidence.
9. THE report SHALL include the current branch name, DynamoDB enrichment field counts, vector metadata enrichment field counts, and whether full `metadata_enrichment` was excluded.

## Non-Goals

- This spec does not delete or recreate DynamoDB tables.
- This spec does not delete S3 buckets or S3 object prefixes.
- This spec does not change KR raw acquisition logic.
- This spec does not redesign TourAPI parsing or city identity reconciliation.
- This spec does not change vector embedding model selection unless current model is proven incorrect.
- This spec does not introduce user-specific scoring or recommendation logic.
- This spec does not perform production routing switch without a separate approval gate.

## Success Criteria

- Terraform and live AWS agree on which Lambda each Step Functions stage calls.
- `VectorStage` no longer calls `kr-pipeline-loader` for vector-build.
- Full vector rebuild is represented as planner plus Step Functions Map plus worker plus aggregator.
- DynamoDB and S3 protected resources remain untouched.
- `visitor_statistics` remains loaded in DynamoDB V2 with 2,820 rows for 235 city PKs x 12 months, or any deviation is explicitly explained and approved.
- `visitor_statistics` remains excluded from S3 Vector rebuild.
- The reset report preserves the branch intent from `investigate/enrichment-field-loading-20260628` and verifies enrichment field loading/backfill status.
- A limited batch run completes without Lambda timeout.
- Failed vector batches can be identified and retried independently.
- A Korean reset report records the exact evidence.

## Open Questions

1. Should old Lambda function names be reused after reset, or should the new vector functions use explicit names such as `kr-pipeline-vector-planner`, `kr-pipeline-vector-worker`, and `kr-pipeline-vector-aggregate`?
2. Should existing CloudWatch log groups be retained for audit continuity or replaced with new retention policy?
3. What is the initial vector batch size: 100, 250, 500, or city-scoped batches?
4. What is the initial Step Functions Map `MaxConcurrency`: 5, 10, or lower to avoid Bedrock throttling?
5. Should the existing `kr-tour-domain-v2` index be reused, recreated, or replaced with a dated target index for the first reset run?
6. Should the five residual legacy/obsolete city PKs without DataLab rows be retained, deprecated, or remapped before the next full data refresh?
7. Should enrichment backfill be completed before the first vector smoke test, or should the smoke test explicitly run in non-enrichment-complete mode?
8. What is the approved first bounded enrichment backfill size if live counts still show zero enrichment fields?
