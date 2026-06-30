# KR Lambda/SFN Batch Reset Completion Report - 2026-06-30

## 1. Executive Summary

완료 여부: `partial`

이번 작업은 `kr-lambda-sfn-batch-reset`의 실행 계층 reset, bounded smoke, 승인된 full vector rebuild, aggregate manifest write, 그리고 최종 evidence 수집까지 완료했다. 다만 active goal을 완전 종료로 선언하지 않고 `partial`로 둔다. 이유는 full rebuild aggregate는 `7662` successful vector writes를 보고했지만 현재 S3 Vector index의 paginated unique count는 `7606`이고, live enrichment-derived field counts가 모두 `0`이므로 enrichment-complete vector output을 주장할 수 없기 때문이다.

| Area | Status | Evidence |
|---|---|---|
| Terraform apply | completed | Task 7 apply `0 added, 5 changed, 0 destroyed`; IAM 보완 apply `0 added, 1 changed, 0 destroyed`; Task 8 vector-only SFN apply `0 added, 1 changed, 0 destroyed`; image package fix apply `0 added, 1 changed, 0 destroyed` |
| Smoke test | completed | planner smoke `batch_count=5`, worker dry-run `item_count=1`, `chunk_count=1`, `failed_count=0`, timeout 없음 |
| Full vector rebuild | completed with residual risk | Step Functions execution `SUCCEEDED`, `redriveCount=1`, aggregate `vector_success_count=7662`, current unique vector count `7606` |
| Visitor statistics | verified | `visitor_statistics_rows=2820`, `visitor_statistics_coverage_ok=true`, `visitor_statistics_vectors=0` |
| Enrichment branch intent | preserved, not complete | branch `investigate/enrichment-field-loading-20260628`, mode `non-enrichment-complete`, enrichment counts all `0` |
| Protected data plane | verified | plan guard passed, protected DynamoDB/S3/S3 Vector resources no-op or no delete/recreate action |

Remaining user decisions:

- `7662` aggregate write count와 `7606` current unique vector count 차이를 follow-up 분석으로 확정할지 결정해야 한다.
- Enrichment backfill을 별도 승인 작업으로 진행할지 결정해야 한다.
- 정리, commit, PR, 재리빌드, vector index reconciliation은 별도 승인 전까지 진행하지 않는다.

## 2. Active Goal Scope Lock

```text
Active goal scope was preserved.
- visitor_statistics coverage: verified, live rows: 2820, city coverage: 235 city PKs x 12 months
- branch intent: investigate/enrichment-field-loading-20260628, enrichment mode: non-enrichment-complete
- protected data plane: verified, destructive protected actions: none
```

Active goal의 세 가지 핵심 범위는 축소하지 않았다.

1. `visitor_statistics` coverage는 DynamoDB V2 live row count, key-shape, vector exclusion으로 재검증했다.
2. `investigate/enrichment-field-loading-20260628`의 enrichment field loading/backfill 의도는 baseline, gate, smoke, rebuild, final report에 유지했다.
3. DynamoDB/S3/S3 Vector protected data-plane 삭제/재생성은 계획과 실행 범위에서 제외했다.

## 3. Visitor Statistics Evidence

| Field | Evidence |
|---|---|
| DataLab raw contract | `raw/KR/datalab/20260629/visitor_statistics_2025.json` |
| local source reference | `data/KR/visitor_statistics_2025.json` |
| DynamoDB table | `TourKoreaDomainDataV2` |
| entity type | `visitor_statistics` |
| live row count | `2820` |
| city coverage | `235 city PKs x 12 months` |
| residual city PKs | `CITY#BUKJEJU`, `CITY#CHEONGWON-GUN`, `CITY#JINHAE`, `CITY#MASAN`, `CITY#NAMJEJU` |
| SK shape | `STAT#{YYYYMM}`; baseline/gate checks reported non-`STAT#` SK count `0` |
| domain_sort_key shape | `STAT#{YYYYMM}`; missing count `0`, mismatch count `0` |
| `gsi_sk` pollution | `0` |
| vector exclusion | S3 Vector paginated count `visitor_statistics_vectors=0`; vector plan/manifest entity counts exclude `visitor_statistics` |

Latest live verifier:

```json
{
  "passed": true,
  "failures": [],
  "observations": {
    "visitor_statistics_rows": 2820,
    "visitor_statistics_coverage_ok": true,
    "enrichment_mode": "non-enrichment-complete"
  }
}
```

Interpretation:

- The stop condition for `visitor_statistics` did not trigger.
- The remaining five legacy/obsolete city PKs are documented identity gaps and were not remediated through vector rebuild.
- `visitor_statistics` remains a DynamoDB/DataLab coverage concern, not a vectorization target.

## 4. Enrichment Field Loading Evidence

| Field | Evidence |
|---|---|
| branch name | `investigate/enrichment-field-loading-20260628` |
| attraction rows | `7024` |
| `metadata_enrichment` count | `0` |
| `indoor_outdoor` count | `0` |
| `vibe_tags` count | `0` |
| `experience_tags` count | `0` |
| `companion_fit` count | `0` |
| `schema_version` count | `0` |
| enrichment mode | `non-enrichment-complete` |
| vector metadata derived field counts | no complete enrichment-derived vector metadata can be claimed because succeeded enrichment rows are `0` |
| full `metadata_enrichment` exclusion | vector metadata tests passed; report does not claim full enrichment metadata output |

Task 8 execution and latest live verifier both report `non-enrichment-complete`. Therefore this report records successful reset/rebuild execution for current live data, but does not claim enrichment-complete vector output.

## 5. Protected Data Plane Evidence

| Resource class | Evidence |
|---|---|
| DynamoDB tables | Terraform plan guard passed; `aws_dynamodb_table.tourkorea_domain_data` and `aws_dynamodb_table.tourkorea_domain_data_v2` stayed `no-op` |
| S3 buckets | Terraform plan guard passed; `aws_s3_bucket.pipeline` and `aws_s3_bucket.pipeline_images` stayed `no-op` |
| S3 objects | No unapproved delete action was run; Task 8 aggregate wrote the approved manifest only |
| S3 Vector index | `lovv-vector-dev` / `kr-tour-domain-v2` was reused; no delete/recreate/replacement was approved or run |
| `terraform_data.kr_vector_index` shim | Terraform plan guard reported `no-op` |

Terraform plan guard command:

```powershell
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
```

Result:

```json
{
  "passed": true,
  "failures": [],
  "protected": {
    "aws_dynamodb_table.tourkorea_domain_data": ["no-op"],
    "aws_dynamodb_table.tourkorea_domain_data_v2": ["no-op"],
    "aws_s3_bucket.pipeline": ["no-op"],
    "aws_s3_bucket.pipeline_images": ["no-op"],
    "terraform_data.kr_vector_index": ["no-op"]
  }
}
```

IAM live check:

```json
{
  "has_dynamodb_delete_item": false,
  "has_s3_delete_object": false,
  "has_dynamodb_scan": true,
  "has_s3vectors_put_vectors": true,
  "action_count": 20
}
```

## 6. Apply And Live Wiring Evidence

### Terraform Apply Evidence

Task 7 apply:

```powershell
terraform -chdir=infrastructure/terraform apply "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

Result:

- `0 added, 5 changed, 0 destroyed`
- Changed resource classes: IAM policy, Lambda functions, Step Functions state machine

Task 7 IAM fix:

- Added `dynamodb:Scan` for `TourKoreaDomainDataV2`
- Apply result: `0 added, 1 changed, 0 destroyed`

Task 8 vector-only path apply:

- Added `CheckVectorOnly` state and `run_vector_only=true` path.
- Apply result: `0 added, 1 changed, 0 destroyed`

Task 8 image package fix:

- Fixed final `GenerateReport` import failure by packaging `kr_image_processor` from the source root and excluding unrelated packages.
- Apply result: `0 added, 1 changed, 0 destroyed`

### Lambda Configuration Evidence

Latest live Lambda configuration summary:

| Function | Handler | Timeout | Memory | Env keys | Layer |
|---|---|---:|---:|---|---|
| `kr-pipeline-transform` | `kr_details_pipeline.handlers.domain_loader_handler.handler` | 900 | 1024 | `DYNAMODB_TABLE`, `IMAGE_BUCKET`, `PROCESSED_PREFIX` | none |
| `kr-pipeline-image` | `kr_image_processor.handlers.image_handler.handler` | 900 | 512 | `IMAGE_BUCKET`, `PIPELINE_BUCKET` | `lovv-requests-layer-dev:1` |
| `kr-pipeline-loader` | `kr_unified_pipeline.handlers.pipeline_handler.handler` | 900 | 512 | `DYNAMODB_TABLE`, `PIPELINE_BUCKET`, `PROCESSED_PREFIX` | none |
| `kr-pipeline-vector` | `kr_vector_index.handlers.vector_index_handler.handler` | 900 | 1024 | `DYNAMODB_TABLE`, `MANIFEST_BUCKET`, `MANIFEST_PREFIX`, `VECTOR_BUCKET`, `VECTOR_INDEX` | none |

Interpretation:

- `kr-pipeline-loader` no longer carries vector env keys.
- `kr-pipeline-vector` owns vector and manifest env keys.
- `kr-pipeline-image` owns report generation and image work.

### Step Functions Evidence

Latest live state machine:

```json
{
  "status": "ACTIVE",
  "start_at": "CheckVectorOnly",
  "has_loader_vector_stage": false,
  "states": [
    {"name": "CheckVectorOnly", "type": "Choice", "default": "CheckSkipTransform"},
    {"name": "VisitorStatsCoverageGate", "type": "Task", "resource": "kr-pipeline-vector", "next": "VisitorStatsCoverageChoice"},
    {"name": "EnrichmentFieldLoadingGate", "type": "Choice", "default": "EnrichmentFieldLoadingFailed"},
    {"name": "VectorPlanStage", "type": "Task", "resource": "kr-pipeline-vector", "next": "VectorBatchStage"},
    {"name": "VectorBatchStage", "type": "Map", "max_concurrency": 5, "next": "VectorAggregateStage"},
    {"name": "VectorAggregateStage", "type": "Task", "resource": "kr-pipeline-vector", "next": "GenerateReport"},
    {"name": "GenerateReport", "type": "Task", "resource": "kr-pipeline-image", "next": "Success"},
    {"name": "LoadStage", "type": "Task", "resource": "kr-pipeline-loader", "next": "VisitorStatsCoverageGate"}
  ]
}
```

Interpretation:

- `VisitorStatsCoverageGate`, `EnrichmentFieldLoadingGate`, `VectorPlanStage`, `VectorBatchStage`, and `VectorAggregateStage` exist.
- There is no live `VectorStage` route that invokes `kr-pipeline-loader` with `command="vector-build"`.
- Vector rebuild is represented as planner plus Map worker plus aggregator.

## 7. Smoke And Rebuild Evidence

### Task 7 Bounded Smoke

Task 7 followed `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`.

Planner smoke:

- target table: `TourKoreaDomainDataV2`
- entity index: `EntityTypeDomainIndex`
- vector bucket/index: `lovv-vector-dev` / `kr-tour-domain-v2`
- item limit: `5`
- batch size: `1`
- result: `batch_count=5`
- entity counts: `{city_metadata: 5}`
- `visitor_statistics`: excluded

Worker smoke:

- mode: `dry_run=true`
- batch: `kr-vector-000001`
- `item_count=1`
- `chunk_count=1`
- `vector_success_count=0`
- `failed_count=0`
- timeout: none

Because the smoke was dry-run, `vector_success_count=0` was expected and no S3 Vector write was attempted in Task 7.

### Task 8 Full Vector Rebuild

Execution ARN:

```text
arn:aws:states:us-east-1:925273580929:execution:kr-data-pipeline-dev:task8-vector-rebuild-20260630-174818
```

Execution status:

```json
{
  "status": "SUCCEEDED",
  "startDate": "2026-06-30T17:48:20.312+09:00",
  "stopDate": "2026-06-30T18:08:29.678+09:00",
  "redriveCount": 1,
  "vectorStatus": "succeeded",
  "batchCount": 240,
  "itemCount": 7662,
  "chunkCount": 7662,
  "vectorSuccessCount": 7662,
  "failedCount": 0,
  "failedBatchCount": 0,
  "failedBatchIds": [],
  "manifestS3Uri": "s3://lovv-data-pipeline-dev-925273580929/processed/KR/vector/manifests/latest.json"
}
```

Initial failure and recovery:

- Initial execution reached final `GenerateReport` and failed with `Runtime.ImportModuleError: No module named 'kr_image_processor'`.
- Image Lambda package source was corrected.
- Execution was redriven once and completed with `SUCCEEDED`.

Manifest:

```json
{
  "index_name": "kr-tour-domain-v2",
  "index_text_mode": "rich",
  "created_at": "2026-06-30T09:00:22.725925+00:00",
  "entity_counts": {
    "city_metadata": 240,
    "attraction": 7024,
    "festival": 398
  },
  "chunk_count": 7662,
  "vector_success_count": 7662,
  "failed_count": 0,
  "status": "succeeded",
  "batch_count": 240,
  "item_count": 7662,
  "failed_batch_ids": []
}
```

S3 Vector paginated unique count:

```json
{
  "vector_count": 7606,
  "visitor_statistics_vectors": 0,
  "metadata_counts": {
    "festival": 393,
    "attraction": 6973,
    "city": 240
  }
}
```

Sample query:

```json
{
  "distanceMetric": "cosine",
  "top_key": "attraction#2765245#0",
  "top_distance": 0.00003063678741455078,
  "top_entity_type": "attraction",
  "top_ddb_pk": "CITY#SEOGWIPO",
  "top_ddb_sk": "ATTRACTION#2765245"
}
```

### Vector Count Discrepancy

The rebuild aggregate and current index inventory differ:

| Entity | Manifest count | Current unique vector count | Delta |
|---|---:|---:|---:|
| attraction | 7024 | 6973 | 51 |
| festival | 398 | 393 | 5 |
| city/city_metadata | 240 | 240 | 0 |
| total | 7662 | 7606 | 56 |

Current interpretation:

- The rebuild did not fail batches; `failed_batch_ids=[]`.
- `visitor_statistics_vectors=0`, so the gap is not caused by visitor statistics inclusion.
- Most likely explanation classes are duplicate vector keys, S3 Vector upsert replacement semantics, stale key replacement, or list inventory semantics.
- This report treats the gap as a residual operational risk. It does not invalidate the verified fact that the Step Functions rebuild completed and sample query works, but it prevents a stronger claim that every aggregate write corresponds to one currently unique vector.

## 8. Review Result

Formal Review Agent pass completed after user approval for Subtask 9.2.

- Severity: Approved
- Area: Spec Alignment
- Evidence: 본 보고서는 Requirement 3, 4, 5, 7, 8, 9에 필요한 visitor statistics, enrichment, protected data-plane, apply, smoke, full rebuild evidence를 포함한다. Task 7/8 산출물과 최신 read-only AWS 조회 결과가 서로 모순되지 않는다.
- Risk: 차단 위험은 없다. 다만 보고서가 의도적으로 `partial` 상태를 유지하므로 active goal을 완전 종료로 오해하면 vector inventory discrepancy와 enrichment 미완료가 누락될 수 있다.
- Required Fix: 없음.
- Retest: `git diff --check`, `terraform validate`, plan guard, live verifier, vector tests를 재실행했다.

- Severity: Approved
- Area: Correctness
- Evidence: Step Functions execution은 `SUCCEEDED`, manifest는 `vector_success_count=7662`, current S3 Vector paginated unique count는 `7606`, `visitor_statistics_vectors=0`으로 기록되어 있다. 보고서는 이 차이를 성공-only summary로 숨기지 않고 residual operational risk로 분리했다.
- Risk: 운영자가 one-to-one item/vector inventory를 전제로 후속 작업을 하면 56개 차이에 대한 원인 분석 없이 품질 판단을 할 수 있다.
- Required Fix: Task 9 완료 전 필수 수정은 없다. 후속 작업으로 duplicate key/upsert/list semantics 분석을 별도 승인받아 진행한다.
- Retest: Task 9.2 검증에서 S3 Vector count와 report grep을 재확인한다.

- Severity: Approved
- Area: Test Coverage
- Evidence: `git diff --check`, `terraform validate`, Terraform plan guard, live verifier, and `src\kr_vector_index\tests`가 통과했다. Task 8에서는 image processor focused tests도 통과했다.
- Risk: 문서-only Task 9.2에 추가 unit test는 필요하지 않다.
- Required Fix: 없음.
- Retest: 최종 검증 명령을 다시 실행한다.

Security review status:

- Severity: Approved
- Area: Workspace Safety
- Evidence: Task 9.2 작업은 workspace 내부 문서와 task plan에 한정되었다. `.env`, `.env.local`, `.envrc`는 `.gitignore`에 포함되어 있고 Git status에 포함되지 않았다.
- Risk: 추가 없음.
- Required Fix: 없음.
- Retest: `git status --short`와 `.gitignore` 확인을 유지한다.

- Severity: Approved
- Area: External API
- Evidence: Task 9.1/9.2의 AWS 작업은 read-only describe/get/list/query 확인으로 제한되었다. 삭제, 재생성, 재리빌드, re-upsert 명령은 실행하지 않았다.
- Risk: 추가 없음.
- Required Fix: 없음.
- Retest: protected data-plane evidence와 plan guard 결과를 최종 검증에서 다시 확인한다.

## Verification Commands And Results

```powershell
git diff --check
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
uv run python -m pytest src\kr_vector_index\tests --basetemp .cache\pytest-vector-index-final -p no:cacheprovider
```

Results:

- `git diff --check`: passed, only line-ending warnings
- `terraform validate`: passed
- Terraform plan guard: passed
- Live verifier: passed
- Vector index tests: `51 passed in 0.36s`

Read-only AWS evidence refreshed:

- Lambda config summary: read successfully
- IAM policy summary: read successfully, delete permissions absent
- Step Functions state machine summary: read successfully, vector Map path present
- Task 8 execution summary: read successfully, `SUCCEEDED`
- Manifest: read successfully
- S3 Vector paginated count: completed, `7606` unique vectors
- Sample query: completed

## Known Limitations And Follow-Up Tasks

- `7662` aggregate successful writes vs `7606` current unique vectors remains unresolved and should be analyzed before relying on one-to-one item/vector inventory.
- Enrichment backfill remains incomplete in live DynamoDB; all tracked enrichment-derived counts are `0`.
- The report can claim reset/rebuild execution success, visitor statistics preservation, vector exclusion, and protected data-plane safety. It cannot claim enrichment-complete vector output.
- No follow-up cleanup, commit, PR, vector reconciliation, or enrichment backfill is approved by this report.

## User Confirmation Items

- Confirm whether to proceed to Subtask 9.2 formal review.
- Confirm whether to analyze the vector count discrepancy as a separate follow-up.
- Confirm whether enrichment backfill should be planned after this reset report.
