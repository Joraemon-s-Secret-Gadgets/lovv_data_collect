# KR Lambda/SFN Batch Reset Active Goal Audit - 2026-06-30

## Audit Timestamp

- 2026-06-30 14:55:12 +09:00

## Purpose

이 문서는 active goal을 작은 완료 범위로 축소하지 않기 위한 현재 상태 감사표다.

Active goal의 필수 범위:

1. 계속 누락되던 `visitor_statistics` / 방문자 통계 coverage를 보완하고 검증한다.
2. 현재 브랜치 `investigate/enrichment-field-loading-20260628`의 enrichment field loading/backfill 의도를 Kiro spec, task plan, verification gates, final report 범위에 유지한다.
3. DynamoDB/S3 protected data-plane 리소스가 accidental deletion 대상이 되지 않게 한다.

이 감사는 non-destructive 상태 점검이다. Terraform apply, live Lambda/SFN 교체, Bedrock embedding write, S3 Vector full rebuild는 실행하지 않았다.

## Current Authoritative Artifacts

| Artifact | Role |
|---|---|
| `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md` | Full source of truth for scope and acceptance criteria |
| `.kiro/specs/kr-lambda-sfn-batch-reset/design.md` | Current target design and gate placement |
| `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md` | Kiro task execution state |
| `docs/reports/TASK6_COMPLETION.md` | Pre-apply plan review completion report |
| `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md` | Apply approval package |
| `docs/reports/kr_lambda_sfn_batch_reset_next_session_handoff_20260630.md` | Next-session handoff package for apply preflight restart |
| `docs/specs/TASK7_SUBTASKS.md` | Next apply and smoke-test instruction sheet |
| `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md` | Final completion evidence gate for visitor statistics, enrichment branch intent, and protected data-plane proof |
| `src/kr_vector_index/live_verification.py` | Read-only post-apply/live drift verifier |
| `src/kr_vector_index/live_verification_cli.py` | CLI entrypoint for the live verifier |
| `src/kr_vector_index/terraform_plan_guard.py` | Non-mutating Terraform plan JSON protected-resource guard |
| `src/kr_vector_index/terraform_plan_guard_cli.py` | CLI entrypoint for the Terraform plan guard |

## Requirement Audit Matrix

| Requirement | Current status | Evidence | Remaining gate |
|---|---|---|---|
| Preserve DynamoDB/S3 protected data plane | Proven for current plan | Terraform plan is `0 to add, 5 to change, 0 to destroy`; plan JSON shows DynamoDB tables, S3 buckets, and `terraform_data.kr_vector_index` as `no-op` | Re-check immediately before apply and after apply |
| Verify `visitor_statistics` coverage | Proven pre-apply | live verifier observes `visitor_statistics_rows=2820` and `visitor_statistics_coverage_ok=true`; gate report documents 235 city PKs x 12 months and key-shape checks | Re-check before apply, after apply, and before full vector rebuild |
| Keep `visitor_statistics` out of vectorization | Covered by spec and tests | requirements/design/tasks require vector exclusion; vector tests and planner gate include exclusion checks | Confirm in post-apply planner smoke output |
| Preserve current branch enrichment/backfill intent | Proven in planning artifacts | requirements, design, tasks, apply approval package, Task 6 report, and Task 7 handoff all name `investigate/enrichment-field-loading-20260628` | Final completion report must repeat branch and live enrichment counts |
| Verify enrichment field loading baseline | Proven pre-apply as incomplete | live verifier reports `enrichment_mode=non-enrichment-complete`; gate report records attraction rows 7,024 and all enrichment field counts 0 | Do not claim enrichment-complete until backfill produces non-zero succeeded rows and vector metadata samples verify allowlisted fields |
| Remove loader-owned vector rebuild path | Proven in desired state only | Terraform plan replaces old `VectorStage -> kr-pipeline-loader command=vector-build` with `kr-pipeline-vector` plan/worker/aggregate states | Requires Terraform apply and post-apply live verifier success |
| Remove runtime delete permissions | Proven in desired state only | Terraform plan removes `dynamodb:DeleteItem` and `s3:DeleteObject` from Lambda execution policy | Requires Terraform apply and post-apply IAM verification |
| Step Functions Map/batch vector workflow | Proven in desired state only | Terraform plan adds `VisitorStatsCoverageGate`, `EnrichmentFieldLoadingGate`, `VectorPlanStage`, `VectorBatchStage`, and `VectorAggregateStage` | Requires Terraform apply and bounded vector planner/worker smoke test |
| Keep verifier tooling out of Lambda runtime package | Proven in desired state | `kr_vector_index/live_verification.py`, `kr_vector_index/live_verification_cli.py`, `kr_vector_index/terraform_plan_guard.py`, and `kr_vector_index/terraform_plan_guard_cli.py` are excluded from `kr-pipeline-vector` archive packaging | Re-check package diff if new verifier modules are added |
| Korean final report | Not yet complete | Task 9 remains open in Kiro task plan; final evidence template now exists at `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md` | Requires Task 7 apply/smoke and Task 8 full rebuild decision first; final report must include visitor statistics evidence, branch `investigate/enrichment-field-loading-20260628`, enrichment loading/backfill status, and protected data-plane proof |

## Current Verification Snapshot

Latest refresh:

- 2026-06-30 14:55:12 +09:00
- `terraform validate`: passed
- `terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"`: still `0 to add, 5 to change, 0 to destroy`
- Terraform plan guard CLI: passed with no protected-resource failures
- Focused plan guard tests: `4 passed`
- Live verifier: expected pre-apply failure, with `visitor_statistics_rows=2820`, `visitor_statistics_coverage_ok=true`, and `enrichment_mode=non-enrichment-complete`

### Terraform

Commands run:

```powershell
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
```

Current result:

- `terraform validate`: passed
- `terraform plan`: `0 to add, 5 to change, 0 to destroy`
- destructive plan action summary: empty
- Terraform plan guard CLI: passed with no protected-resource failures
- protected resources:
  - `aws_dynamodb_table.tourkorea_domain_data`: `no-op`
  - `aws_dynamodb_table.tourkorea_domain_data_v2`: `no-op`
  - `aws_s3_bucket.pipeline`: `no-op`
  - `aws_s3_bucket.pipeline_images`: `no-op`
  - `terraform_data.kr_vector_index`: `no-op`

### Live Read-Only Verifier

Command run:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Current result:

- exit code: `1`
- this is expected before Terraform apply because live AWS still has old drift
- observed data gates:
  - `visitor_statistics_rows=2820`
  - `visitor_statistics_coverage_ok=true`
  - `enrichment_mode=non-enrichment-complete`

Expected pre-apply failures:

- `kr-pipeline-loader` still carries `VECTOR_BUCKET`
- `kr-pipeline-loader` still carries `VECTOR_INDEX`
- loader description still mentions vector rebuild
- Lambda IAM policy still allows `dynamodb:DeleteItem`
- Lambda IAM policy still allows `s3:DeleteObject`
- live Step Functions is missing the new visitor/enrichment/vector Map states
- live Step Functions still routes vector-build to `kr-pipeline-loader`

### Diff Hygiene

Command run:

```powershell
git diff --check
```

Result:

- passed
- only Git line-ending warnings were reported

### Terraform Plan Guard Test

Command run:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m pytest src\kr_vector_index\tests\test_terraform_plan_guard.py src\kr_vector_index\tests\test_terraform_plan_guard_cli.py --basetemp .cache\pytest-plan-guard-cli -p no:cacheprovider
```

Result:

- `4 passed`

Focused CLI test:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m pytest src\kr_vector_index\tests --basetemp .cache\pytest-vector-index-plan-guard-cli -p no:cacheprovider
```

Result:

- `49 passed`

## Completion Status

The active goal is not complete.

Completed or proven pre-apply:

- Kiro requirements/design/tasks preserve `visitor_statistics` and enrichment branch intent.
- `visitor_statistics` live coverage is currently verified as 2,820 rows with coverage OK.
- enrichment baseline is currently verified as `non-enrichment-complete`.
- Terraform desired state protects DynamoDB/S3/S3 Vector resources from deletion.
- Terraform plan guard now codifies the protected-resource delete/recreate check before apply.
- Terraform plan guard CLI now provides the Task 7 command surface without an inline Python one-liner.
- Terraform archive excludes verifier/plan-guard helper modules from the `kr-pipeline-vector` Lambda ZIP.
- Terraform desired state removes loader vector ownership and runtime delete permissions.
- Task 7 handoff exists and keeps apply/smoke work approval-gated.

Still required before goal completion:

1. Explicit user approval for Terraform apply.
2. Apply the reviewed plan artifact.
3. Run post-apply live verifier until old loader vector routing and delete permissions are gone.
4. Run bounded vector planner smoke test.
5. Run bounded vector worker smoke test, dry-run unless live write approval is explicit.
6. Decide whether enrichment backfill must complete before full vector rebuild or only before claiming enrichment-complete output.
7. Request explicit approval before any full vector rebuild.
8. Write the final Korean completion report using `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`, with visitor statistics evidence, branch name, enrichment counts, vector metadata evidence, protected data-plane proof, apply evidence, smoke evidence, full rebuild status, and remaining risks.

## Stop Conditions

Stop immediately if any of these occur:

- Terraform plan changes to delete or recreate protected DynamoDB/S3 resources.
- `visitor_statistics` live count drops below 2,820 without approved source-of-truth change.
- post-apply Step Functions still routes vector build through loader.
- post-apply Lambda IAM still includes `dynamodb:DeleteItem` or `s3:DeleteObject`.
- vector smoke test reaches timeout.
- a report claims enrichment-complete while live enrichment counts remain zero.
- any task requires reading or changing files outside this workspace.
