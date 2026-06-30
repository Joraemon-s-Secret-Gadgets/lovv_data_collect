# TASK7_SUBTASKS: KR Lambda/SFN Apply And Smoke Verification

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Task Plan: `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`
> Apply Approval Package: `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
> Active Goal Audit: `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`
> Next-Session Handoff: `docs/reports/kr_lambda_sfn_batch_reset_next_session_handoff_20260630.md`
> Apply Smoke Runbook: `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`
> Task 9 Final Evidence Template: `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`
> Previous Task Report: `docs/reports/TASK6_COMPLETION.md`
> Progress Report: `docs/reports/kr_lambda_sfn_batch_reset_implementation_progress_20260630.md`
> Base branch: `investigate/enrichment-field-loading-20260628`
> Responsible role: Implementation Agent, then Review Agent

## Context And Dependencies

Task 7 starts only after the user explicitly approves Terraform apply.

Pre-apply evidence already exists:

- `visitor_statistics` coverage is 2,820 rows and coverage OK.
- enrichment mode is `non-enrichment-complete`, with enrichment-derived live counts still 0.
- Terraform plan artifact is `.cache/terraform/kr-lambda-sfn-batch-reset.tfplan`.
- Latest reviewed plan is `0 to add, 5 to change, 0 to destroy`.
- DynamoDB tables, S3 buckets, and S3 Vector Terraform shim are no-op in the plan.
- live AWS still has old drift before apply:
  - `VectorStage -> kr-pipeline-loader` with `command="vector-build"`.
  - Lambda execution policy still includes `dynamodb:DeleteItem` and `s3:DeleteObject`.
- A read-only live verification helper exists at `src/kr_vector_index/live_verification.py`.
- A read-only live verification CLI exists at `python -m kr_vector_index.live_verification_cli`.
- A non-mutating Terraform plan guard exists at `src/kr_vector_index/terraform_plan_guard.py`.
- A non-mutating Terraform plan guard CLI exists at `python -m kr_vector_index.terraform_plan_guard_cli`.
- The verifier and plan-guard modules are intentionally excluded from the `kr-pipeline-vector` Lambda ZIP.
- Task 6 completion evidence is recorded in `docs/reports/TASK6_COMPLETION.md`.
- Active goal completion status is tracked in `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`; do not mark the goal complete while Task 7, Task 8, or the final report remain open.
- Next-session restart order and approval boundaries are summarized in `docs/reports/kr_lambda_sfn_batch_reset_next_session_handoff_20260630.md`.
- Exact post-apply smoke commands and write boundaries are fixed in `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`.
- Task 9 final evidence requirements are fixed in `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`; Task 7 and Task 8 handoffs must preserve `visitor_statistics`, branch `investigate/enrichment-field-loading-20260628`, enrichment field loading/backfill, and protected data-plane evidence for that report.

Pre-approval maintenance may refresh the plan, plan guard output, and live verifier observations without starting Task 7. Task 7 implementation itself still starts only after explicit user approval for Terraform apply.

Implementation must start at Subtask 1 and proceed in order. After each Subtask is implemented and locally or live-verified, stop and report verification results before moving to the next Subtask.

## Expected Pre-Apply Verifier Interpretation

Before Terraform apply, `python -m kr_vector_index.live_verification_cli` is expected to exit `1` because live AWS still has old execution-plane drift.

This is acceptable only when all of the following remain true:

- failures are limited to old loader vector routing, old loader vector environment, old delete permissions, and missing desired Step Functions vector gate/stage states;
- observations still include `visitor_statistics_rows=2820`;
- observations still include `visitor_statistics_coverage_ok=true`;
- observations still include the current enrichment mode, currently `non-enrichment-complete`;
- Terraform plan guard still reports protected DynamoDB/S3/S3 Vector resources as `no-op`.

After Terraform apply, the same live verifier must pass. A post-apply verifier failure is a Task 7 blocker, not an expected condition.

The apply approval package and active goal audit should be refreshed whenever these pre-apply checks are rerun:

- `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
- `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`

## Deadlock Escape Conditions

Stop and escalate to the user after:

- any Terraform plan changes from the approved `0 add, 5 change, 0 destroy` shape;
- any plan action includes DynamoDB table delete/recreate, S3 bucket delete/recreate, S3 object deletion, or S3 Vector index deletion;
- three consecutive failures of the same Terraform, AWS, or smoke verification command;
- any live `visitor_statistics` coverage drop below 2,820 rows without an approved explanation;
- Step Functions still routes vector build to loader after apply;
- Lambda IAM still includes delete permissions after apply;
- vector planner or worker smoke test reaches Lambda timeout;
- enrichment is reported as complete while live enrichment field counts remain 0;
- any need to access files outside this workspace.

## Subtask 1: Confirm Apply Approval And Refresh Plan Guard

- Purpose: Terraform apply must run only against the reviewed plan shape and only after explicit user approval.
- Required Context:
  - Apply approval has not yet been granted.
  - The approved command must use the saved plan artifact, not a freshly unreviewed ad-hoc plan.
- Context Budget:
  - Must read:
    - `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
    - `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`
    - `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md#7-apply-and-smoke-test-after-approval`
    - `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md#requirement-5-terraform-managed-reset`
  - Do not read:
    - `.env` files.
    - `AGENTS.ko.md`.
    - Large logs or build artifacts.
  - Optional read:
    - `docs/reports/kr_lambda_sfn_batch_reset_implementation_progress_20260630.md` for recent plan evidence.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-5-terraform-managed-reset`
  - `#success-criteria`
- Must Read Before Implementation:
  - `#requirement-5-terraform-managed-reset`
  - `#success-criteria`
- Target Files:
  - `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
  - `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`
  - `.cache/terraform/kr-lambda-sfn-batch-reset.tfplan`
- Out of Scope:
  - Running Terraform apply before explicit user approval.
  - Regenerating plan and applying it without reporting the new action summary.
- Acceptance Criteria:
  - User approval for Terraform apply is explicit in the current conversation.
  - `terraform plan` still reports `0 to add, 5 to change, 0 to destroy`.
  - Plan JSON confirms protected DynamoDB/S3/S3 Vector resources remain no-op.
  - Latest preflight still records `visitor_statistics` coverage OK and accurate enrichment mode.
  - Pre-apply live verifier failure, if rerun before apply, is interpreted only under `Expected Pre-Apply Verifier Interpretation` and is documented in the approval package.
- Verification:
  - `terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"`
  - `terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"`
  - `terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli`
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m kr_vector_index.live_verification_cli`
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run python -c "import json; from kr_vector_index.handlers.vector_index_handler import handler; print(json.dumps(handler({'command':'preflight'}, None), ensure_ascii=False, default=str))"`

## Subtask 2: Apply Approved Terraform Plan

- Purpose: Bring the live Lambda/SFN execution plane into the reviewed Terraform desired state while preserving the protected data plane.
- Required Context:
  - The saved plan updates Lambda code/configuration, the Step Functions state machine, and Lambda IAM policy.
  - DynamoDB tables and S3 buckets must remain untouched.
- Context Budget:
  - Must read:
    - `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md#terraform-plan-summary`
    - `infrastructure/terraform/main.tf`
    - `infrastructure/terraform/step_functions.tf`
  - Do not read:
    - `.env` files.
    - Unrelated docs/reports deletions already present in the dirty worktree.
  - Optional read:
    - Terraform output only if apply fails.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-5-terraform-managed-reset`
  - `#non-goals`
- Must Read Before Implementation:
  - `#requirement-5-terraform-managed-reset`
  - `#non-goals`
- Target Files:
  - No source file edits expected.
  - Apply output should be summarized in a report, not stored as a raw log unless needed for failure analysis.
- Out of Scope:
  - Manual AWS Console deletion.
  - `aws lambda delete-function`.
  - DynamoDB or S3 deletion.
- Acceptance Criteria:
  - Terraform apply exits successfully against the approved saved plan.
  - No DynamoDB table, S3 bucket, or S3 Vector index deletion occurs.
  - Apply result is summarized in Korean with any warnings or failures.
- Verification:
  - `terraform -chdir=infrastructure/terraform apply "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"`
  - Capture Terraform resource action summary from apply output.

## Subtask 3: Verify Live Lambda, IAM, And Step Functions Wiring

- Purpose: Prove live AWS now matches the desired execution-plane split and no longer routes vector rebuild through loader.
- Required Context:
  - Before apply, live AWS still had old loader vector routing and delete permissions.
  - After apply, those should be removed.
- Context Budget:
  - Must read:
    - `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md#post-apply-smoke-checklist`
    - `infrastructure/terraform/step_functions.tf`
    - `src/kr_vector_index/live_verification.py`
  - Do not read:
    - Large CloudWatch logs unless a verification command fails.
  - Optional read:
    - Lambda configuration JSON returned by AWS CLI.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-8-책임-분리`
  - `#success-criteria`
- Must Read Before Implementation:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-8-책임-분리`
  - `#success-criteria`
- Target Files:
  - `docs/reports/kr_lambda_sfn_batch_reset_implementation_progress_20260630.md`
  - Later completion report under `docs/reports/`
- Out of Scope:
  - Full vector rebuild.
  - Mutating DynamoDB or S3 data.
- Acceptance Criteria:
  - `kr-pipeline-loader` no longer carries `VECTOR_BUCKET` or `VECTOR_INDEX`.
  - Lambda execution policy no longer includes `dynamodb:DeleteItem`.
  - Lambda execution policy no longer includes `s3:DeleteObject`.
  - Step Functions includes `VisitorStatsCoverageGate` before vector planning.
  - Step Functions includes `EnrichmentFieldLoadingGate` before vector planning.
  - Step Functions includes `VectorBatchStage` Map with bounded concurrency.
  - Step Functions invokes `kr-pipeline-vector` for vector planner, worker, and aggregate stages.
  - Step Functions no longer invokes loader for `command="vector-build"`.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m kr_vector_index.live_verification_cli`
  - Use `src/kr_vector_index/live_verification.py` to evaluate the collected live AWS snapshot.
  - `aws lambda get-function-configuration --function-name kr-pipeline-loader --region us-east-1`
  - `aws lambda get-function-configuration --function-name kr-pipeline-vector --region us-east-1`
  - `aws iam get-role-policy --role-name lovv-data-pipeline-lambda-dev --policy-name lovv-data-pipeline-lambda-policy-dev --region us-east-1`
  - `aws stepfunctions describe-state-machine --state-machine-arn arn:aws:states:us-east-1:925273580929:stateMachine:kr-data-pipeline-dev --region us-east-1`

## Subtask 4: Run Vector Planner Smoke Test

- Purpose: Verify the new vector Lambda can produce a bounded batch plan without starting a full rebuild.
- Required Context:
  - `visitor_statistics` must remain excluded.
  - enrichment mode is currently `non-enrichment-complete`.
- Context Budget:
  - Must read:
    - `src/kr_vector_index/handlers/vector_index_handler.py`
    - `src/kr_vector_index/preflight.py`
    - `src/kr_vector_index/batch.py`
  - Do not read:
    - Full DynamoDB exports.
    - Large S3 objects.
  - Optional read:
    - Focused vector test files if local behavior is unclear.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-3-visitor_statistics-coverage-보존-및-누락-보완-gate`
  - `#requirement-4-현재-브랜치-enrichment-field-loading-의도-보존`
  - `#requirement-7-step-functions-map-기반-vector-분할`
- Must Read Before Implementation:
  - `#requirement-3-visitor_statistics-coverage-보존-및-누락-보완-gate`
  - `#requirement-4-현재-브랜치-enrichment-field-loading-의도-보존`
  - `#requirement-7-step-functions-map-기반-vector-분할`
- Target Files:
  - No source file edits expected.
  - Smoke result should be summarized in `docs/reports/`.
- Out of Scope:
  - Full vector rebuild.
  - Bulk S3 Vector writes.
- Acceptance Criteria:
  - Planner returns a small bounded batch descriptor set.
  - Planner summary records `visitor_statistics_coverage_ok=true`.
  - Planner summary records enrichment mode accurately.
  - Planner excludes `visitor_statistics` from vectorizable items.
  - No full rebuild starts.
- Verification:
  - Invoke `kr-pipeline-vector` with `command="preflight"` and inspect `coverage_ok`.
  - Invoke `kr-pipeline-vector` with `command="plan"`, small `max_items`, and small `batch_size`.
  - Confirm response includes batch descriptors and no `visitor_statistics` items.

## Subtask 5: Run One Bounded Vector Worker Smoke Test

- Purpose: Prove one worker-sized batch completes without Lambda timeout and reports retryable failures if they occur.
- Required Context:
  - This subtask may call Bedrock and S3 Vectors if not run in dry-run mode.
  - If live writes are not explicitly approved, run dry-run only.
- Context Budget:
  - Must read:
    - `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md#post-apply-smoke-checklist`
    - `src/kr_vector_index/handlers/vector_index_handler.py`
    - `src/kr_vector_index/aggregate.py`
    - `src/kr_vector_index/batch.py`
  - Do not read:
    - Large CloudWatch logs unless smoke fails or times out.
  - Optional read:
    - `src/kr_vector_index/tests/test_vector_index_handler_batch.py`.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Must Read Before Implementation:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Target Files:
  - No source file edits expected.
  - Smoke result should be summarized in `docs/reports/`.
- Out of Scope:
  - Full VectorBatchStage execution.
  - Claiming enrichment-complete rebuild while live enrichment counts remain zero.
- Acceptance Criteria:
  - One bounded batch completes before Lambda timeout.
  - Worker returns item counts, vector counts, failure counts, and failed item or batch details when applicable.
  - If live write mode is used, writes target only the approved vector bucket/index.
  - Stop before full rebuild.
- Verification:
  - Invoke one planner-derived worker descriptor with dry-run unless write approval is explicit.
  - If write mode is approved, verify the target index is `lovv-vector-dev` / `kr-tour-domain-v2`.
  - Record duration, item count, chunk count, vector success count, and failures.

## Subtask 6: Review Gate And Task 7 Handover Report

- Purpose: Confirm Task 7 is complete enough to decide whether to proceed to full vector rebuild approval.
- Required Context:
  - Full rebuild is Task 8 and still requires separate approval.
  - Completion must preserve visitor statistics and enrichment branch intent.
- Context Budget:
  - Must read:
    - Changed reports from Subtasks 1-5.
    - `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md#8-full-vector-rebuild-after-smoke-test-approval`
    - `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md#success-criteria`
  - Do not read:
    - Unrelated deleted historical reports.
  - Optional read:
    - CloudWatch excerpts only if smoke failure needs diagnosis.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-9-검증-보고-및-운영-인수인계`
  - `#success-criteria`
- Must Read Before Implementation:
  - `#requirement-9-검증-보고-및-운영-인수인계`
  - `#success-criteria`
- Target Files:
  - `docs/reports/TASK7_COMPLETION.md`
  - `docs/specs/TASK8_SUBTASKS.md`
  - `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`
  - `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`
- Out of Scope:
  - Starting full vector rebuild.
  - Marking the entire goal complete if Task 8 or final completion report remains open.
- Acceptance Criteria:
  - Task 7 completion report includes apply output, live wiring verification, IAM verification, visitor statistics gate, enrichment mode, smoke test result, and remaining risks.
  - Task 7 completion report follows the smoke evidence requirements in `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`.
  - Task 8 subtask sheet is created for full vector rebuild approval and execution.
  - Task 8 handoff references the Task 9 final evidence template or carries forward equivalent final-report evidence requirements.
  - `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md` is updated only for subtasks actually completed and verified.
  - User is asked for explicit approval before Task 8 begins.
- Verification:
  - `git diff --check`
  - `terraform -chdir=infrastructure/terraform validate`
  - `uv run python -m pytest src\kr_vector_index\tests\test_terraform_plan_guard.py src\kr_vector_index\tests\test_terraform_plan_guard_cli.py --basetemp .cache\pytest-plan-guard -p no:cacheprovider`
  - Relevant `uv run pytest` and `uv run ruff check` commands for any source files changed during Task 7.
