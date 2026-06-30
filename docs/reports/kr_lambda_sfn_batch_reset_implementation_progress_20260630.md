# KR Lambda/SFN Batch Reset Implementation Progress - 2026-06-30

## Summary

이번 작업은 `kr-lambda-sfn-batch-reset` goal의 다음 구현 단계를 로컬 코드와 Terraform desired state까지 진행한 것이다.

Current branch intent preserved in this reset scope: `investigate/enrichment-field-loading-20260628`.

실행한 범위:

- `kr-pipeline-vector` Lambda에 `preflight`, `plan`, `worker`, `aggregate` command를 추가했다.
- Step Functions desired state를 단일 `VectorStage`에서 `preflight -> plan -> Map(worker) -> aggregate` 구조로 변경했다.
- `visitor_statistics` coverage gate와 enrichment field loading gate를 vector rebuild 앞에 배치했다.
- `aggregate` command가 batch 결과를 S3 manifest로 기록하고 `succeeded`/`partial`/`failed` 상태를 반환하도록 보강했다.
- `plan` command가 preflight의 `enrichment_mode`와 `visitor_statistics_coverage_ok`를 summary에 보존하도록 보강했다.
- `kr-pipeline-loader` handler에서 `vector-build`/`e2e` command와 `kr_vector_index` import 경로를 제거했다.
- Lambda execution role Terraform desired state에서 `dynamodb:DeleteItem`과 `s3:DeleteObject` 권한을 제거했다.
- Terraform plan을 생성해 DynamoDB/S3 protected data-plane 삭제가 없는지 확인했다.

실행하지 않은 범위:

- `terraform apply`
- Lambda/SFN live 교체
- DynamoDB/S3 삭제
- S3 Vector full rebuild

## Code Changes

### Vector Lambda Commands

New modules:

- `src/kr_vector_index/aggregate.py`
- `src/kr_vector_index/batch.py`
- `src/kr_vector_index/live_verification.py`
- `src/kr_vector_index/live_verification_cli.py`
- `src/kr_vector_index/preflight.py`

Updated handler:

- `src/kr_vector_index/handlers/vector_index_handler.py`

Supported command surface now includes:

| Command | Purpose |
|---|---|
| `preflight` | read-only visitor statistics and enrichment field gate summary |
| `plan` | export vectorizable items and create city PK + offset/limit batch descriptors |
| `worker` | process exactly one bounded batch descriptor |
| `aggregate` | aggregate Step Functions Map worker results and write final manifest |
| `export-counts` | existing count command |
| `build` | existing single-invocation build command retained for compatibility |

The Step Functions path should use `preflight`, `plan`, `worker`, and `aggregate`, not the legacy full `build` path.

Aggregate output now includes:

- `status`: `succeeded`, `partial`, or `failed`
- `failed_batch_ids`
- `manifest_s3_uri` when `MANIFEST_BUCKET` is configured
- final manifest body with `entity_counts`, `batch_count`, `item_count`, `chunk_count`, `vector_success_count`, and failed batch ids

Plan output now preserves preflight context:

- `enrichment_mode`: copied from `$.data_gates.summary.enrichment.mode`
- `visitor_statistics_coverage_ok`: copied from `$.data_gates.summary.visitor_statistics.coverage_ok`

### Loader Lambda Responsibility Split

Updated handler:

- `src/kr_unified_pipeline/handlers/pipeline_handler.py`

Updated tests:

- `src/kr_unified_pipeline/tests/test_pipeline_handler_routing.py`
- `src/kr_unified_pipeline/tests/test_pipeline_handler_load_phase.py`
- `src/kr_vector_index/tests/test_live_verification.py`
- `src/kr_vector_index/tests/test_live_verification_cli.py`

Current loader command surface:

| Command | Purpose |
|---|---|
| `load` | read processed S3 items and write DynamoDB |
| `preprocess` | retained legacy preprocessing route |

The loader handler now rejects `vector-build` and `e2e` with HTTP-style `statusCode=400`. This prevents Step Functions or ad-hoc invocations from falling back to the old single-Lambda vector rebuild path.

## Terraform Changes

Updated files:

- `infrastructure/terraform/main.tf`
- `infrastructure/terraform/step_functions.tf`
- `infrastructure/terraform/variables.tf`
- `infrastructure/terraform/terraform.tfvars.example`

New variables:

| Variable | Default | Purpose |
|---|---:|---|
| `kr_vector_batch_size` | 250 | max vectorizable DynamoDB items per worker invocation |
| `kr_vector_map_max_concurrency` | 5 | max concurrent vector worker invocations |

State machine desired flow:

1. `LoadStage`
2. `VisitorStatsCoverageGate`
3. `VisitorStatsCoverageChoice`
4. `EnrichmentFieldLoadingGate`
5. `VectorPlanStage`
6. `VectorBatchStage` Map
7. `VectorAggregateStage`
8. `GenerateReport`

`VectorAggregateStage` now passes `$.vector_plan.summary.entity_counts` into `aggregate`, so the final manifest keeps the same entity-count baseline that the planner used.

`VectorPlanStage` also passes visitor/enrichment gate context from `VisitorStatsCoverageGate`/`EnrichmentFieldLoadingGate` into `plan`, so the planner summary records whether the rebuild is running in `enrichment-complete` or `non-enrichment-complete` mode.

Important routing correction:

- live AWS still has `VectorStage -> kr-pipeline-loader command=vector-build`
- local Terraform desired state now removes that route and uses `kr-pipeline-vector`
- loader Lambda ZIP excludes `kr_vector_index/**`
- loader Lambda environment no longer carries `VECTOR_BUCKET` or `VECTOR_INDEX`

IAM tightening:

- Terraform desired state removes `dynamodb:DeleteItem` from the Lambda execution role DynamoDB statements.
- Terraform desired state removes `s3:DeleteObject` from the Lambda execution role S3 statement.
- Runtime delete API search found no delete calls under `src/`; the only remaining delete usage is the explicit cleanup utility `scripts/cleanup_dynamodb_v1_non_target.py`, outside the Lambda package runtime path.

## Gate Status

### Visitor Statistics

Live read-only verification remains:

- `visitor_statistics` rows: 2,820
- distinct city PKs: 235
- `gsi_sk` anomaly count: 0
- non-`STAT#` SK count: 0
- missing `domain_sort_key` count: 0
- `domain_sort_key != SK` count: 0

`visitor_statistics` remains excluded from vectorization.

Latest pre-apply read-only `preflight` result:

- expected rows: 2,820
- row count: 2,820
- coverage: OK
- `gsi_sk` count: 0
- non-`STAT#` SK count: 0
- missing `domain_sort_key` count: 0
- non-`STAT#` `domain_sort_key` count: 0

### Enrichment Field Loading

Live read-only verification remains:

- attraction rows: 7,024
- `metadata_enrichment`: 0
- `indoor_outdoor`: 0
- `vibe_tags`: 0
- `experience_tags`: 0
- `companion_fit`: 0
- `schema_version`: 0

Therefore, full vector rebuild may verify timeout/wiring after apply, but must not be reported as enrichment-complete until enrichment backfill produces non-zero successful rows and vector metadata samples confirm those fields.

Latest pre-apply read-only `preflight` result:

- attraction rows: 7,024
- mode: `non-enrichment-complete`
- `metadata_enrichment`: 0
- `indoor_outdoor`: 0
- `vibe_tags`: 0
- `experience_tags`: 0
- `companion_fit`: 0
- `schema_version`: 0

## Verification

### Python Tests

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m pytest src\kr_unified_pipeline\tests src\kr_vector_index\tests src\kr_details_pipeline\tests\test_domain_loader_handler.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_visitor_statistics_backfill.py
```

Result: 282 passed.

### Python Lint

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run ruff check src\kr_vector_index src\kr_unified_pipeline\handlers\pipeline_handler.py src\kr_unified_pipeline\tests\test_pipeline_handler_routing.py src\kr_unified_pipeline\tests\test_pipeline_handler_load_phase.py src\kr_details_pipeline\handlers\domain_loader_handler.py src\kr_details_pipeline\enrichment_persistence.py src\kr_details_pipeline\visitor_statistics_backfill.py src\kr_details_pipeline\tests\test_domain_loader_handler.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_visitor_statistics_backfill.py
```

Result: all checks passed.

Follow-up verification cleanup:

- `src/kr_vector_index/tests/test_metadata.py` import order and unused import were cleaned up.
- The ruff command now includes the full `src\kr_vector_index` test/runtime tree and passes.
- Focused vector aggregate/handler/metadata command passed: 26 passed.
- Focused live verifier and CLI command passed: 4 passed.
- Full vector index test command passed: 45 passed.
- Full goal regression command passed: 282 passed.

### Kiro Task Plan Status

Updated:

- `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`

Completed through pre-apply gate:

- Task 2: live baseline and drift report
- Task 3: visitor_statistics and enrichment field loading gates
- Task 4: Terraform execution-plane reset preparation
- Task 5: vector batch runtime
- Task 6: Terraform plan review before apply

Still open:

- Task 7+: Terraform apply, live Lambda/SFN wiring verification, vector smoke test, full rebuild, and completion report require explicit approval before proceeding.

### Terraform

Commands:

```powershell
terraform -chdir=infrastructure/terraform fmt -check
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

Results:

- `terraform fmt -check`: passed
- `terraform validate`: passed
- `terraform plan`: `0 to add, 5 to change, 0 to destroy`

Plan action summary:

| Resource | Action |
|---|---|
| `aws_dynamodb_table.tourkorea_domain_data` | no-op |
| `aws_dynamodb_table.tourkorea_domain_data_v2` | no-op |
| `aws_s3_bucket.pipeline` | no-op |
| `aws_s3_bucket.pipeline_images` | no-op |
| `terraform_data.kr_vector_index` | no-op |
| `aws_iam_role_policy.pipeline_lambda_policy` | update |
| `aws_lambda_function.kr_pipeline_loader` | update |
| `aws_lambda_function.kr_pipeline_transform` | update |
| `aws_lambda_function.kr_pipeline_vector` | update |
| `aws_sfn_state_machine.kr_data_pipeline` | update |

Protected data-plane status:

- DynamoDB tables: no delete, no recreate
- S3 buckets: no delete, no recreate
- S3 Vector index Terraform shim: no-op
- Plan destroy count: 0
- Lambda execution role desired state: `dynamodb:DeleteItem` and `s3:DeleteObject` removed

Live AWS apply-pending status:

- `aws iam get-role-policy` still shows live `dynamodb:DeleteItem` and `s3:DeleteObject` in `lovv-data-pipeline-lambda-policy-dev`; this is expected until the approved Terraform plan is applied.
- `aws stepfunctions describe-state-machine` still shows live `VectorStage -> kr-pipeline-loader` with `command="vector-build"`; this is the live drift that the Terraform desired state removes.
- `aws lambda get-function-configuration kr-pipeline-loader` still shows vector environment variables (`VECTOR_BUCKET`, `VECTOR_INDEX`) and the old loader description; this is also expected until apply.
- `aws lambda get-function-configuration kr-pipeline-vector` confirms the dedicated vector Lambda exists and carries `MANIFEST_BUCKET`/`MANIFEST_PREFIX` for aggregate manifest output.
- `src/kr_vector_index/live_verification.py` was run against current live AWS and correctly failed pre-apply because loader vector env vars, live delete permissions, and old loader vector routing still remain.
- `uv run python -m kr_vector_index.live_verification_cli` was run against current live AWS and correctly exited `1` pre-apply because loader vector env vars, live delete permissions, and old loader vector routing still remain.
- The same verifier observed `visitor_statistics_rows=2820`, `visitor_statistics_coverage_ok=true`, and `enrichment_mode=non-enrichment-complete`.

Note: loader and transform Lambda code hashes also changed in the plan because the Terraform archive data sources package the current dirty worktree. Review those source deltas before apply.

### Local Handler Smoke

Vector command surface was driven locally with live AWS read-only access and worker dry-run:

- `preflight`: returned `visitor_statistics.coverage_ok=true`, row count 2,820, and enrichment mode `non-enrichment-complete`.
- `plan`: with `max_items=5` and `batch_size=2`, returned 5 city-scoped batch descriptors.
- `worker`: ran against the first batch with `dry_run=True`, produced 2 chunks and 0 vector writes.

No Bedrock call or S3 Vector write was executed during this smoke test.

Loader command surface was also driven locally:

```powershell
uv run python -c "from kr_unified_pipeline.handlers.pipeline_handler import handler; print(handler({'command':'vector-build'}, None)); print(handler({'command':'e2e','bucket':'test-bucket'}, None))"
```

Result:

- `vector-build`: `statusCode=400`, supported commands are `['load', 'preprocess']`
- `e2e`: `statusCode=400`, supported commands are `['load', 'preprocess']`

## Stop Gate

Apply approval package:

- `docs/reports/TASK6_COMPLETION.md`
- `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
- `docs/specs/TASK7_SUBTASKS.md`

Do not run:

```powershell
terraform -chdir=infrastructure/terraform apply "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

until the user explicitly approves the plan.

Before apply approval, review:

1. Lambda ZIP source deltas for transform and loader.
2. Step Functions definition diff.
3. protected data-plane no-op summary.
4. live enrichment field count remaining at 0.
5. live AWS still carries old vector routing and delete permissions until Terraform apply.
