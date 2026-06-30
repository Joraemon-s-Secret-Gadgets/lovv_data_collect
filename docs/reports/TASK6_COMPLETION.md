# TASK6 Completion Report: KR Lambda/SFN Plan Review Before Apply

## Completion Timestamp

- 2026-06-30 14:06:56 +09:00

## Responsible Agent

- Main Codex as Implementation/Review coordinator

## Scope

Task 6 reviewed the Terraform plan before apply for the `kr-lambda-sfn-batch-reset` spec.

This task did not run Terraform apply, replace live Lambda/SFN resources, delete DynamoDB/S3 resources, run a full vector rebuild, or claim enrichment-complete vector output.

## Spec Alignment Checklist

| Requirement | Status | Evidence |
|---|---|---|
| Stop before Terraform apply unless user explicitly approves | Satisfied | `terraform apply` was not executed |
| Produce a Terraform plan artifact before apply | Satisfied | `.cache/terraform/kr-lambda-sfn-batch-reset.tfplan` |
| Review protected data-plane resource actions | Satisfied | Plan JSON shows DynamoDB tables, S3 buckets, and S3 Vector Terraform shim as `no-op` |
| Preserve `visitor_statistics` coverage gate | Satisfied | latest preflight observed `visitor_statistics_rows=2820` and coverage OK |
| Preserve branch enrichment/backfill intent | Satisfied | reports and Task 7 handoff preserve `investigate/enrichment-field-loading-20260628` and `non-enrichment-complete` mode |
| Confirm expected execution-plane changes | Satisfied | plan updates Lambda IAM policy, loader Lambda, transform Lambda, vector Lambda, and Step Functions |
| Stop before full vector rebuild | Satisfied | Task 8 remains separate and unapproved |

## Changed Files And Implementation Summary

Primary Task 6 artifacts:

- `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`
- `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
- `docs/reports/kr_lambda_sfn_batch_reset_implementation_progress_20260630.md`
- `docs/specs/TASK7_SUBTASKS.md`
- `src/kr_vector_index/live_verification.py`
- `src/kr_vector_index/live_verification_cli.py`
- `src/kr_vector_index/tests/test_live_verification.py`
- `src/kr_vector_index/tests/test_live_verification_cli.py`
- `src/kr_vector_index/terraform_plan_guard.py`
- `src/kr_vector_index/terraform_plan_guard_cli.py`
- `src/kr_vector_index/tests/test_terraform_plan_guard.py`
- `src/kr_vector_index/tests/test_terraform_plan_guard_cli.py`

Task 6 also depends on earlier implementation files that produced the reviewed plan:

- `infrastructure/terraform/main.tf`
- `infrastructure/terraform/step_functions.tf`
- `infrastructure/terraform/variables.tf`
- `infrastructure/terraform/terraform.tfvars.example`
- `src/kr_vector_index/aggregate.py`
- `src/kr_vector_index/batch.py`
- `src/kr_vector_index/preflight.py`
- `src/kr_vector_index/handlers/vector_index_handler.py`
- `src/kr_unified_pipeline/handlers/pipeline_handler.py`

Implementation summary:

- Reviewed the Terraform plan and confirmed `0 to add, 5 to change, 0 to destroy`.
- Confirmed protected DynamoDB/S3/S3 Vector resources are `no-op`.
- Removed Lambda execution role delete permissions from Terraform desired state.
- Preserved `visitor_statistics` and enrichment gates before vector planning.
- Added Task 7 apply/smoke handoff instructions.
- Added read-only live verifier and CLI so post-apply drift can be checked without manual interpretation.
- Added non-mutating Terraform plan guard so protected DynamoDB/S3/S3 Vector delete or recreate actions fail before apply.
- Added non-mutating Terraform plan guard CLI so Task 7 can run the guard without an inline Python command.
- Excluded verifier and plan-guard helper modules from the `kr-pipeline-vector` Lambda ZIP so apply packages contain runtime code only.

## Verification Results

### Terraform

Commands:

```powershell
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

Results:

- `terraform validate`: passed
- `terraform plan`: `0 to add, 5 to change, 0 to destroy`
- Plan JSON protected resources:
  - `aws_dynamodb_table.tourkorea_domain_data`: `no-op`
  - `aws_dynamodb_table.tourkorea_domain_data_v2`: `no-op`
  - `aws_s3_bucket.pipeline`: `no-op`
  - `aws_s3_bucket.pipeline_images`: `no-op`
  - `terraform_data.kr_vector_index`: `no-op`
- Terraform plan guard result: passed, no protected-resource failures

Expected update resources:

- `aws_iam_role_policy.pipeline_lambda_policy`
- `aws_lambda_function.kr_pipeline_loader`
- `aws_lambda_function.kr_pipeline_transform`
- `aws_lambda_function.kr_pipeline_vector`
- `aws_sfn_state_machine.kr_data_pipeline`

### Python

Commands:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m pytest src\kr_unified_pipeline\tests src\kr_vector_index\tests src\kr_details_pipeline\tests\test_domain_loader_handler.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_visitor_statistics_backfill.py --basetemp .cache\pytest-goal-regression -p no:cacheprovider
uv run ruff check src\kr_vector_index
```

Results:

- Goal regression pytest scope: `282 passed`
- Full `src\kr_vector_index\tests`: `49 passed`
- Focused live verifier and CLI tests: `4 passed`
- Focused Terraform plan guard and CLI tests: `4 passed`
- `ruff check src\kr_vector_index`: passed

### Live Read-Only Verification

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Current pre-apply result:

- Exit code: `1`
- Expected failure before apply because live AWS still has old drift:
  - loader still carries `VECTOR_BUCKET`
  - loader still carries `VECTOR_INDEX`
  - loader description still mentions vector rebuild
  - Lambda IAM policy still allows `dynamodb:DeleteItem`
  - Lambda IAM policy still allows `s3:DeleteObject`
  - live Step Functions still routes vector build to loader
- Positive observations:
  - `visitor_statistics_rows=2820`
  - `visitor_statistics_coverage_ok=true`
  - `enrichment_mode=non-enrichment-complete`

### Diff Hygiene

Command:

```powershell
git diff --check
```

Result: passed. Only Git line-ending warnings were reported.

## Items Requiring User Confirmation

Task 7 must not start until the user explicitly approves Terraform apply.

Before approving Task 7, review:

1. `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
2. `docs/specs/TASK7_SUBTASKS.md`
3. Terraform plan summary: `0 to add, 5 to change, 0 to destroy`
4. Protected data-plane status: DynamoDB/S3/S3 Vector resources are `no-op`
5. Current enrichment mode: `non-enrichment-complete`

## Remaining Risks

- Live AWS still has old vector routing and live delete permissions until Terraform apply runs successfully.
- Full vector rebuild is not approved and not executed.
- Enrichment-derived fields remain zero in live DynamoDB, so vector rebuild cannot be reported as enrichment-complete.
- Loader and transform Lambda package hashes include the current dirty worktree; source deltas must remain reviewed before apply.

## Next-Agent Instruction Sheet

- `docs/specs/TASK7_SUBTASKS.md`

Start with Subtask 1 only after explicit user approval for Terraform apply.
