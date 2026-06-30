# KR Lambda/SFN Batch Reset Gate Report - 2026-06-30

## Summary

이 문서는 `kr-lambda-sfn-batch-reset` Kiro spec에 추가된 두 개의 non-negotiable gate를 현재 상태 기준으로 검증한 보고서다.

- Gate 1: 계속 누락되던 `visitor_statistics` coverage를 Terraform reset 및 full vector rebuild 전에 검증한다.
- Gate 2: 현재 브랜치 `investigate/enrichment-field-loading-20260628`의 enrichment field loading/backfill 의도를 reset 과정에서 유지한다.

이번 확인은 read-only 검증과 로컬 테스트만 수행했다. DynamoDB/S3 삭제, Terraform apply, S3 Vector rebuild는 수행하지 않았다.

## Scope

### In Scope

- Kiro spec: `.kiro/specs/kr-lambda-sfn-batch-reset/`
- Visitor statistics source and live table verification
- Enrichment persistence/backfill and vector metadata local verification
- DynamoDB/S3 protected data-plane deletion 방지 gate

### Out of Scope

- Terraform apply
- Lambda/SFN replacement
- S3 Vector full rebuild
- DynamoDB/S3 object deletion
- Existing vector index deletion or recreation

## Kiro Spec Alignment

Updated spec artifacts:

- `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- `.kiro/specs/kr-lambda-sfn-batch-reset/design.md`
- `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`

The spec now includes:

- `Requirement 3: visitor_statistics coverage 보존 및 누락 보완 gate`
- `Requirement 4: 현재 브랜치 enrichment field loading 의도 보존`
- `VisitorStatsCoverageGate` before vector planning
- `EnrichmentFieldLoadingGate` before vector planning
- Task 3: `Close visitor_statistics and enrichment field loading gates`

## Visitor Statistics Gate

### Source Contract

- Local source: `data/KR/visitor_statistics_2025.json`
- S3 raw contract: `raw/KR/datalab/20260629/visitor_statistics_2025.json`
- Live table: `TourKoreaDomainDataV2`
- Entity type: `visitor_statistics`

### Live Read-Only Evidence

Read-only DynamoDB checks were run against `TourKoreaDomainDataV2` in `us-east-1`.

| Check | Result |
|---|---:|
| `visitor_statistics` rows | 2,820 |
| distinct city PKs | 235 |
| rows per city PK | 12 for all 235 PKs |
| covered months | `STAT#202501` through `STAT#202512` |
| rows with `gsi_sk` | 0 |
| rows with non-`STAT#` SK | 0 |
| rows missing `domain_sort_key` | 0 |
| rows where `domain_sort_key != SK` | 0 |

The remaining full-coverage gap is the documented five legacy/obsolete city PKs without matching DataLab source:

- `CITY#BUKJEJU`
- `CITY#CHEONGWON-GUN`
- `CITY#JINHAE`
- `CITY#MASAN`
- `CITY#NAMJEJU`

### Vector Boundary

`visitor_statistics` remains a DynamoDB/DataLab coverage concern. It must not be used as a vector rebuild fix path.

Required invariant:

- `visitor_statistics` is stored in DynamoDB V2.
- `visitor_statistics` is excluded from S3 Vector rebuild.

## Enrichment Field Loading Gate

### Branch Intent

Current branch intent to preserve:

- Branch: `investigate/enrichment-field-loading-20260628`
- Concern: enrichment field loading/backfill must remain part of reset planning, verification gates, and final reporting.

### Fields in Scope

- `metadata_enrichment`
- `indoor_outdoor`
- `vibe_tags`
- `experience_tags`
- `companion_fit`
- `schema_version`

### Required Invariants

- Succeeded enrichment writes top-level derived fields and `metadata_enrichment`.
- Failed or skipped enrichment does not clobber unrelated DynamoDB fields.
- Vector metadata may include allowed derived fields only when `metadata_enrichment.status="succeeded"`.
- Vector metadata must not include the full `metadata_enrichment` object.
- If live enrichment counts are zero or unknown, completion report must not claim enrichment-complete vector rebuild.

### Live Read-Only Evidence

Read-only DynamoDB checks were run against `TourKoreaDomainDataV2` in `us-east-1`.

| Check | Result |
|---|---:|
| attraction rows | 7,024 |
| rows with `metadata_enrichment` | 0 |
| rows with `indoor_outdoor` | 0 |
| rows with `vibe_tags` | 0 |
| rows with `experience_tags` | 0 |
| rows with `companion_fit` | 0 |
| rows with `schema_version` | 0 |

Conclusion: enrichment loading/backfill is still required before any report can claim an enrichment-complete vector rebuild.

## Verification Commands

### Visitor Statistics Local Verification

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m pytest src\kr_details_pipeline\tests\test_visitor_statistics_backfill.py src\kr_details_pipeline\tests\test_load.py src\kr_details_pipeline\tests\test_domain_preprocess.py src\kr_vector_index\tests\test_export.py --basetemp .cache\pytest-visitor -p no:cacheprovider
```

Result: 20 passed.

### Enrichment and Vector Metadata Local Verification

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m pytest src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrich_attraction.py src\kr_vector_index\tests --basetemp .cache\pytest-enrichment -p no:cacheprovider
```

Result: 62 passed.

### Live DynamoDB Read-Only Checks

Read-only checks confirmed:

- `visitor_statistics` count: 2,820
- `gsi_sk` anomaly count: 0
- non-`STAT#` SK count: 0
- `domain_sort_key` missing count: 0
- `domain_sort_key != SK` count: 0
- distinct visitor statistic city PK count: 235
- attraction count: 7,024
- `metadata_enrichment` count: 0
- enrichment derived field counts: 0 for each field

## Protected Data-Plane Gate

Before any Terraform apply, plan review must still confirm:

- no DynamoDB table delete or recreate
- no S3 bucket delete or recreate
- no S3 object delete action
- no S3 Vector index delete unless separately approved
- no reset step removes `visitor_statistics` rows
- no reset step wipes enrichment fields

## Current Status

| Area | Status |
|---|---|
| Kiro spec gate coverage | complete for requirements/design/tasks |
| visitor_statistics live coverage | verified read-only |
| visitor_statistics local tests | passed |
| enrichment persistence/backfill local tests | passed |
| vector metadata local tests | passed |
| live enrichment field counts | verified as 0 |
| Terraform apply | not run |
| Lambda/SFN replacement | not run |
| S3 Vector full rebuild | not run |

## Next Required Gate

The next approval-gated task is Task 7 execution from `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md` and `docs/specs/TASK7_SUBTASKS.md`.

Current pre-apply artifacts to keep attached to Task 7:

1. `docs/reports/TASK6_COMPLETION.md`
2. `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
3. `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`
4. `docs/specs/TASK7_SUBTASKS.md`

Task 7 must still stop before Terraform apply unless the user explicitly approves apply in the current conversation.
