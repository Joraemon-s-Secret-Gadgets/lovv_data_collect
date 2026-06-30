# KR Lambda/SFN Batch Reset Apply Approval Package - 2026-06-30

## Purpose

이 문서는 `kr-lambda-sfn-batch-reset` 작업의 Terraform apply 승인 전 확인 패키지다.

Apply approval target:

- Terraform plan artifact: `.cache/terraform/kr-lambda-sfn-batch-reset.tfplan`
- Active goal audit: `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`
- Next-session handoff: `docs/reports/kr_lambda_sfn_batch_reset_next_session_handoff_20260630.md`
- Task 6 completion report: `docs/reports/TASK6_COMPLETION.md`
- Apply command:

```powershell
terraform -chdir=infrastructure/terraform apply "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

Do not run the command until the user explicitly approves Terraform apply.

## Non-Negotiable Scope

1. `visitor_statistics` coverage must remain loaded and verified.
2. Current branch intent `investigate/enrichment-field-loading-20260628` must remain in the reset, verification gates, and final report.
3. DynamoDB tables, S3 buckets, existing S3 objects, and S3 Vector index resources must not be deleted.

## Current Live AWS State Before Apply

Read-only AWS checks confirm the live execution plane has not been updated yet.

| Area | Live state before apply |
|---|---|
| Step Functions | `VectorStage` still invokes `kr-pipeline-loader` with `command="vector-build"` |
| Loader Lambda | still has vector environment variables `VECTOR_BUCKET` and `VECTOR_INDEX` |
| Lambda IAM policy | still includes `dynamodb:DeleteItem` and `s3:DeleteObject` |
| Vector Lambda | dedicated `kr-pipeline-vector` exists and has manifest environment variables |

This live drift is the expected target of the Terraform plan.

## Latest Non-Destructive Refresh

Refresh timestamp:

- 2026-06-30 14:55:12 +09:00

Commands rerun:

```powershell
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
uv run python -m pytest src\kr_vector_index\tests\test_terraform_plan_guard.py src\kr_vector_index\tests\test_terraform_plan_guard_cli.py --basetemp .cache\pytest-plan-guard-refresh -p no:cacheprovider
```

Refresh result:

- `terraform validate`: passed.
- `terraform plan`: still `0 to add, 5 to change, 0 to destroy`.
- Terraform plan guard CLI: passed, no protected-resource failures.
- Protected resources remain `no-op`: `TourKoreaDomainData`, `TourKoreaDomainDataV2`, `lovv-data-pipeline-dev-925273580929`, `lovv-pipeline-images-dev-925273580929`, and `terraform_data.kr_vector_index`.
- Plan guard focused tests: `4 passed`.
- Live verifier exits `1`, expected before apply, because live AWS still has old loader vector routing and delete permissions.
- Live verifier observations remain: `visitor_statistics_rows=2820`, `visitor_statistics_coverage_ok=true`, `enrichment_mode=non-enrichment-complete`.

## Terraform Plan Summary

Latest reviewed plan result:

```text
Plan: 0 to add, 5 to change, 0 to destroy.
```

Expected changed resources:

| Resource | Action | Reason |
|---|---|---|
| `aws_iam_role_policy.pipeline_lambda_policy` | update | remove Lambda runtime delete permissions |
| `aws_lambda_function.kr_pipeline_loader` | update | loader-only responsibility split |
| `aws_lambda_function.kr_pipeline_transform` | update | current package hash from shared transform package |
| `aws_lambda_function.kr_pipeline_vector` | update | vector planner/worker/aggregate runtime; verifier/plan-guard helper modules are excluded from the Lambda ZIP |
| `aws_sfn_state_machine.kr_data_pipeline` | update | add preflight, Map worker, aggregate, and gates |

Protected resource action summary:

| Protected resource | Plan action |
|---|---|
| `aws_dynamodb_table.tourkorea_domain_data` | no-op |
| `aws_dynamodb_table.tourkorea_domain_data_v2` | no-op |
| `aws_s3_bucket.pipeline` | no-op |
| `aws_s3_bucket.pipeline_images` | no-op |
| `terraform_data.kr_vector_index` | no-op |

## Visitor Statistics Gate

Latest pre-apply read-only `preflight` result:

| Check | Result |
|---|---:|
| expected rows | 2,820 |
| live rows | 2,820 |
| coverage | OK |
| `gsi_sk` count | 0 |
| non-`STAT#` SK count | 0 |
| missing `domain_sort_key` count | 0 |
| non-`STAT#` `domain_sort_key` count | 0 |

`visitor_statistics` remains a DynamoDB/DataLab coverage concern and must remain excluded from vectorization.

## Enrichment Field Loading Gate

Current branch intent to preserve: `investigate/enrichment-field-loading-20260628`.

Latest pre-apply read-only `preflight` result:

| Field | Live count |
|---|---:|
| attraction rows | 7,024 |
| `metadata_enrichment` | 0 |
| `indoor_outdoor` | 0 |
| `vibe_tags` | 0 |
| `experience_tags` | 0 |
| `companion_fit` | 0 |
| `schema_version` | 0 |

Current mode: `non-enrichment-complete`.

After apply, vector smoke tests may verify routing, timeout behavior, batch slicing, and manifest output. They must not be reported as enrichment-complete until enrichment backfill produces non-zero successful rows and sampled vector metadata confirms allowed enrichment-derived fields.

## Apply Approval Checklist

Before running apply, confirm:

- The user explicitly approved Terraform apply.
- The active goal audit still says Task 7 is the next approval-gated step.
- The plan artifact path is still `.cache/terraform/kr-lambda-sfn-batch-reset.tfplan`.
- Plan remains `0 to add, 5 to change, 0 to destroy`.
- DynamoDB tables remain no-op.
- S3 buckets remain no-op.
- S3 Vector index Terraform shim remains no-op.
- `visitor_statistics` preflight still reports 2,820 rows and coverage OK.
- enrichment preflight still records mode accurately, currently `non-enrichment-complete`.

## Post-Apply Smoke Checklist

Task 7 handoff/subtask sheet:

- `docs/specs/TASK7_SUBTASKS.md`
- Apply/smoke command runbook: `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`

Read-only live verifier:

- `src/kr_vector_index/live_verification.py`
- `src/kr_vector_index/live_verification_cli.py`
- focused test: `src/kr_vector_index/tests/test_live_verification.py`
- focused CLI test: `src/kr_vector_index/tests/test_live_verification_cli.py`
- command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Non-mutating Terraform plan guard:

- `src/kr_vector_index/terraform_plan_guard.py`
- `src/kr_vector_index/terraform_plan_guard_cli.py`
- focused test: `src/kr_vector_index/tests/test_terraform_plan_guard.py`
- focused CLI test: `src/kr_vector_index/tests/test_terraform_plan_guard_cli.py`
- Terraform ZIP boundary: `live_verification.py`, `live_verification_cli.py`, `terraform_plan_guard.py`, and `terraform_plan_guard_cli.py` are excluded from `kr-pipeline-vector` Lambda packaging.
- command:

```powershell
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
```

After apply, run read-only live verification before any full vector rebuild:

1. Verify Lambda configurations:
   - `kr-pipeline-loader` no longer carries vector environment variables.
   - `kr-pipeline-loader` description reflects S3-to-DynamoDB load responsibility.
   - `kr-pipeline-vector` carries vector and manifest environment variables.
2. Verify IAM:
   - Lambda execution policy no longer includes `dynamodb:DeleteItem`.
   - Lambda execution policy no longer includes `s3:DeleteObject`.
3. Verify Step Functions:
   - `LoadStage` flows to `VisitorStatsCoverageGate`.
   - `EnrichmentFieldLoadingGate` remains before vector planning.
   - vector rebuild path invokes `kr-pipeline-vector`, not `kr-pipeline-loader`.
   - `VectorBatchStage` uses Map with bounded concurrency.
   - `VectorAggregateStage` writes final manifest.
4. Run vector planner smoke test with a small item limit, following `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`.
5. Run vector worker smoke test with one bounded batch and `dry_run=true` unless live write approval is explicit.
6. Do not invoke `aggregate` during dry-run-only smoke because it may write a manifest to S3 when `MANIFEST_BUCKET` is configured.
7. Stop before full vector rebuild until smoke results are reviewed and approved.

Current pre-apply verifier result is expected to fail because live AWS still has old routing and live delete permissions. The CLI currently exits `1` and reports `visitor_statistics_rows=2820`, `visitor_statistics_coverage_ok=true`, and `enrichment_mode=non-enrichment-complete`.

## Stop Conditions

Stop immediately if any of the following occurs:

- Terraform plan changes to include DynamoDB or S3 deletion.
- live `visitor_statistics` coverage drops below 2,820 rows without an approved explanation.
- Step Functions still routes vector build to loader after apply.
- Lambda IAM still includes delete permissions after apply.
- vector smoke test reaches timeout.
- enrichment mode is reported as complete while live enrichment counts remain zero.
