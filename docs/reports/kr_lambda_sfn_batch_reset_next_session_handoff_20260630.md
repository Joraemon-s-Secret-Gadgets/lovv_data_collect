# KR Lambda/SFN Batch Reset Next-Session Handoff - 2026-06-30

## Session Scope Lock

이번 세션의 목표는 다음 세션이 바로 apply 전 재검증부터 시작할 수 있도록 repo-local handoff 패키지를 정리하는 데서 멈춘다.

이번 세션에서 실행하지 않은 작업:

- Terraform apply
- AWS Lambda invoke
- Step Functions execution
- non-dry-run vector worker
- aggregate manifest write
- full vector rebuild

다음 세션의 시작점은 Task 7 `Confirm Apply Approval And Refresh Plan Guard`이다. apply는 사용자 명시 승인 전까지 실행하지 않는다.

## Current Completed State

| Artifact | Current state | Next-session use |
|---|---|---|
| `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md` | 존재함. protected data-plane, `visitor_statistics`, enrichment branch intent, Lambda layer, Step Functions Map/batch worker 요구사항을 포함한다. | source of truth로 다시 읽는다. |
| `.kiro/specs/kr-lambda-sfn-batch-reset/design.md` | 존재함. Lambda/SFN 실행계층 재구성, `VisitorStatsCoverageGate`, `EnrichmentFieldLoadingGate`, `VectorPlanStage`, `VectorBatchStage`, `VectorAggregateStage` 설계를 포함한다. | apply 후 live wiring 검증 기준으로 사용한다. |
| `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md` | 존재함. Task 1.3과 Task 2-6은 완료, Task 1.1/1.2와 Task 7-9는 체크되지 않은 상태다. Apply approval package는 이미 Task 7 시작용으로 준비되어 있다. | Task 7 실행 전 Task 1.1/1.2 승인 경계가 여전히 충족되는지 확인하고, Task 7부터 순서대로 진행한다. |
| `docs/specs/TASK7_SUBTASKS.md` | 존재함. apply 전 재검증, apply, post-apply verifier, bounded smoke 순서를 고정한다. | 다음 세션의 직접 실행 지시서다. |
| `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md` | 존재함. apply 이후 smoke command와 write boundary를 고정한다. | post-apply verifier 통과 후에만 bounded smoke에 사용한다. |
| `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md` | 존재함. 최종 완료 보고서의 필수 증적을 고정한다. | Task 9에서 목표 축소 방지용 evidence gate로 사용한다. |
| `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md` | 존재함. apply 승인 전 패키지와 2026-06-30 14:55 KST 기준 refresh 결과를 포함한다. | apply 승인 전 최신성 확인 후 갱신한다. |
| `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md` | 존재함. active goal이 visitor/enrichment/protected-data-plane 범위를 잃지 않도록 감사표를 제공한다. | 목표 완료 여부 판단 전에 다시 갱신한다. |
| `src/kr_vector_index/live_verification.py` and `src/kr_vector_index/live_verification_cli.py` | 존재함. read-only live drift verifier다. | apply 전에는 예상 실패 해석, apply 후에는 반드시 성공해야 하는 gate로 사용한다. |
| `src/kr_vector_index/terraform_plan_guard.py` and `src/kr_vector_index/terraform_plan_guard_cli.py` | 존재함. saved plan JSON의 protected-resource delete/recreate를 차단한다. | apply 전 plan guard로 반드시 재실행한다. |

## Verification Evidence Snapshot

### Rechecked In This Handoff Session

Timestamp: 2026-06-30 15:25 KST.

| Check | Command | Result |
|---|---|---|
| Terraform validate | `terraform -chdir=infrastructure/terraform validate` | passed |
| Saved Terraform plan summary | `terraform -chdir=infrastructure/terraform show -no-color "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"` | `Plan: 0 to add, 5 to change, 0 to destroy.` |
| Plan guard | `terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" \| uv run python -m kr_vector_index.terraform_plan_guard_cli` | passed, `failures=[]` |
| Vector-related tests | `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m pytest src\kr_vector_index\tests --basetemp .cache\pytest-vector-index-handoff -p no:cacheprovider` | `51 passed` |
| Ruff | `$env:UV_CACHE_DIR='.cache\uv'; uv run ruff check src\kr_vector_index` | passed |
| Diff whitespace/conflict check | `git diff --check` | exit code 0; only existing LF to CRLF warnings were printed |

Protected resources confirmed as `no-op` by the saved plan guard:

- `aws_dynamodb_table.tourkorea_domain_data`
- `aws_dynamodb_table.tourkorea_domain_data_v2`
- `aws_s3_bucket.pipeline`
- `aws_s3_bucket.pipeline_images`
- `terraform_data.kr_vector_index`

### Recorded Pre-Apply Live Snapshot

Latest recorded live verifier snapshot: 2026-06-30 14:55 KST in `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md` and `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`.

Pre-apply `kr_vector_index.live_verification_cli` failure is expected because live AWS has not received the Terraform execution-plane reset yet.

The expected pre-apply observations must remain:

- `visitor_statistics_rows=2820`
- `visitor_statistics_coverage_ok=true`
- `enrichment_mode=non-enrichment-complete`

Expected pre-apply live drift:

- `kr-pipeline-loader` still carries vector environment variables.
- Lambda execution policy still allows `dynamodb:DeleteItem`.
- Lambda execution policy still allows `s3:DeleteObject`.
- live Step Functions still routes vector build through loader or lacks the desired gate/stage shape.

Any live verifier result outside this expected drift set must stop the apply path.

## Next-Session Start Order

1. Read this handoff package.
2. Read `docs/specs/TASK7_SUBTASKS.md`.
3. Read `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`.
4. Confirm the current branch is still `investigate/enrichment-field-loading-20260628`.
5. Regenerate the Terraform plan or explicitly confirm the saved plan is still current.
6. Confirm the plan is still `0 to add, 5 to change, 0 to destroy`.
7. Run the Terraform plan guard again.
8. Reconfirm protected resources are `no-op`:
   - `aws_dynamodb_table.tourkorea_domain_data`
   - `aws_dynamodb_table.tourkorea_domain_data_v2`
   - `aws_s3_bucket.pipeline`
   - `aws_s3_bucket.pipeline_images`
   - `terraform_data.kr_vector_index`
9. Run `kr_vector_index.live_verification_cli` before apply and interpret exit code `1` only if the observations and expected old drift match this handoff.
10. Ask for explicit user approval before Terraform apply.
11. Run Terraform apply only against the reviewed saved plan artifact.
12. Immediately run `kr_vector_index.live_verification_cli` after apply.
13. Treat any post-apply verifier failure as a blocker.
14. Only after the post-apply verifier passes, proceed with bounded smoke from `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`.

Recommended pre-apply commands:

```powershell
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -no-color "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Apply command, only after approval:

```powershell
terraform -chdir=infrastructure/terraform apply "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

Post-apply required verifier:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

## Approval Boundaries

The following actions require separate explicit user approval:

- Terraform apply
- non-dry-run vector worker execution
- aggregate command because it can write a manifest to S3 when `MANIFEST_BUCKET` is configured
- full vector rebuild through Step Functions or any equivalent path
- S3 Vector index deletion, recreation, or replacement

Task 7 bounded smoke defaults:

- planner smoke may use a small item limit after apply and live verifier success.
- worker smoke must use `dry_run=true` unless live write approval is explicit.
- aggregate must not run during dry-run-only smoke.
- full rebuild is not part of Task 7.

## Final Goal Scope To Preserve

Do not mark the active goal complete until all of the following remain true and are proven with current evidence:

- 방문자 통계 누락 방지: `visitor_statistics` remains loaded with 2,820 rows, coverage OK, correct `STAT#{YYYYMM}` key shape, and vector exclusion evidence.
- Branch intent preservation: `investigate/enrichment-field-loading-20260628` remains named in the spec, task plan, verification gates, smoke report, and final report.
- Enrichment field loading/backfill: live counts and vector metadata rules are reported; do not claim enrichment-complete while enrichment field counts remain zero.
- DynamoDB/S3/S3 Vector data-plane protection: no protected delete/recreate is present in plan/apply evidence.
- Lambda 계층화: layer/package boundary remains explicit and is not claimed as the timeout fix.
- Step Functions Map or batch worker structure: vector rebuild is represented by planner, bounded Map/batch worker, and aggregator instead of one full-rebuild Lambda invocation.
- Apply 후 실증 기반 완료 보고: final Korean completion report follows `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md` and includes apply, live verifier, bounded smoke, rebuild decision/result, visitor statistics, enrichment, and protected-resource evidence.

## Stop Conditions For Next Session

Stop before apply if:

- Terraform plan is no longer `0 to add, 5 to change, 0 to destroy`.
- Any protected DynamoDB/S3/S3 Vector resource has delete or recreate action.
- `visitor_statistics_rows` is missing or below 2,820 without approved explanation.
- `visitor_statistics_coverage_ok` is not `true`.
- enrichment mode is missing or falsely reported as complete while live enrichment counts remain zero.
- the current branch intent is dropped from any apply/smoke/final-report gate.

Stop after apply if:

- post-apply live verifier exits non-zero.
- Step Functions still routes vector build to loader.
- Lambda IAM still includes `dynamodb:DeleteItem` or `s3:DeleteObject`.
- bounded vector smoke reaches timeout.
- aggregate, non-dry-run worker, or full rebuild would run without separate approval.
