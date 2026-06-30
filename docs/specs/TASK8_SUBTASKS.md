# TASK8_SUBTASKS: KR Full Vector Rebuild Approval And Execution

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Task Plan: `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`
> Previous Task Report: `docs/reports/TASK7_COMPLETION.md`
> Apply Smoke Runbook: `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`
> Final Evidence Template: `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`
> Base branch: `investigate/enrichment-field-loading-20260628`
> Responsible role: Implementation Agent, then Review Agent

## Context And Dependencies

Task 8 starts only after Task 7 smoke has passed and the user explicitly approves full vector rebuild execution.

Task 7 verified:

- Terraform apply completed with `0 added, 5 changed, 0 destroyed`.
- Additional IAM fix for `dynamodb:Scan` completed with `0 added, 1 changed, 0 destroyed`.
- Post-apply live verifier passed with exit code `0`.
- `visitor_statistics_rows=2820`.
- `visitor_statistics_coverage_ok=true`.
- `enrichment_mode=non-enrichment-complete`.
- Planner smoke returned `batch_count=5` for the bounded sample.
- Planner smoke returned `entity_counts={city_metadata: 5}` and excluded `visitor_statistics`.
- Worker dry-run smoke completed for `batch_id=kr-vector-000001`.
- Worker dry-run recorded `item_count=1`, `chunk_count=1`, `vector_success_count=0`, `failed_count=0`.
- Task 7 did not run aggregate or full rebuild.

Task 8 is the first point where actual vector writes may occur. Dry-run smoke success does not authorize non-dry-run writes.

## Approval Boundaries

Before Subtask 2 starts, the user must explicitly approve all of the following:

- full Step Functions vector rebuild execution;
- non-dry-run vector worker writes to the approved S3 Vector target;
- aggregate execution and manifest write behavior;
- target vector bucket and index, expected default `lovv-vector-dev` / `kr-tour-domain-v2`;
- Map `MaxConcurrency` or equivalent concurrency limit;
- retry policy for failed batches;
- no S3 Vector index deletion, recreation, or replacement unless separately approved.

If approval is partial, execute only the approved portion and record the unapproved portion as blocked or deferred.

## Deadlock Escape Conditions

Stop and escalate to the user after:

- missing or ambiguous approval for real writes, aggregate, target index, or full rebuild;
- post-Task 7 live verifier regresses to non-zero exit;
- `visitor_statistics_rows` drops below 2,820 without approved explanation;
- `visitor_statistics_coverage_ok` is not `true`;
- planner includes `visitor_statistics` in vectorizable batches;
- three consecutive batch failures with the same failure mode;
- any unapproved protected data-plane delete/recreate action appears;
- aggregate writes an unexpected manifest path or cannot write the manifest after approved execution;
- enrichment is reported as complete while live enrichment field counts remain zero.

## Subtask 1: Request Full Rebuild Approval

- Purpose: 실제 vector write와 aggregate manifest write가 시작되기 전에 Task 7 smoke 증거와 비용/실패 위험을 사용자에게 제시하고 승인을 받는다.
- Required Context:
  - Task 7 smoke passed but only in bounded dry-run mode.
  - Full rebuild may write vectors and aggregate manifest data.
- Context Budget:
  - Must read:
    - `docs/reports/TASK7_COMPLETION.md`
    - `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md#8-full-vector-rebuild-after-smoke-test-approval`
    - `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md#requirement-7-step-functions-map-기반-vector-분할`
    - `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md#requirement-9-검증-보고-및-운영-인수인계`
  - Do not read:
    - `.env` files.
    - Large CloudWatch logs unless Task 7 smoke evidence is disputed.
    - Full DynamoDB exports.
  - Optional read:
    - `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Must Read Before Implementation:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Target Files:
  - `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_approval_20260630.md`
- Out of Scope:
  - Starting Step Functions execution.
  - Running worker in non-dry-run mode.
  - Running aggregate.
- Acceptance Criteria:
  - Approval package summarizes Task 7 duration/count/failure evidence.
  - Approval package asks for explicit approval for non-dry-run writes.
  - Approval package asks for explicit approval for aggregate execution and manifest writes.
  - Approval package confirms target bucket/index and concurrency.
  - Approval package confirms no S3 Vector index deletion/recreation is approved.
- Verification:
  - Manual review of the approval package.
  - Stop and wait for explicit user approval.

## Subtask 2: Refresh Live Gates Before Full Rebuild

- Purpose: Task 7 이후 live AWS 상태가 full rebuild 시작 조건을 유지하는지 재확인한다.
- Required Context:
  - Post-apply verifier passed at the end of Task 7.
  - Full rebuild must not start if visitor/enrichment/protected-data-plane gates regress.
- Context Budget:
  - Must read:
    - `docs/reports/TASK7_COMPLETION.md#verification-results`
    - `src/kr_vector_index/live_verification.py`
  - Do not read:
    - Large logs or full exports.
  - Optional read:
    - `src/kr_vector_index/preflight.py`
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-3-visitor_statistics-coverage-보존-및-누락-보완-gate`
  - `#requirement-4-현재-브랜치-enrichment-field-loading-의도-보존`
  - `#success-criteria`
- Must Read Before Implementation:
  - `#requirement-3-visitor_statistics-coverage-보존-및-누락-보완-gate`
  - `#requirement-4-현재-브랜치-enrichment-field-loading-의도-보존`
  - `#success-criteria`
- Target Files:
  - `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_progress_20260630.md`
- Out of Scope:
  - Full rebuild execution before gates pass.
- Acceptance Criteria:
  - Live verifier exits `0`.
  - `visitor_statistics_rows` remains at least `2820`.
  - `visitor_statistics_coverage_ok=true`.
  - Enrichment mode is recorded and not overstated.
  - Current branch remains `investigate/enrichment-field-loading-20260628`.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m kr_vector_index.live_verification_cli`
  - Record the verifier result in the progress report.

## Subtask 3: Run Approved Full Vector Batch Workflow

- Purpose: 승인된 target과 concurrency로 Step Functions full vector rebuild를 시작하고 실행 ID를 확보한다.
- Required Context:
  - User approval must explicitly cover real writes and aggregate.
  - Planner must exclude `visitor_statistics`.
- Context Budget:
  - Must read:
    - `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_approval_20260630.md`
    - `infrastructure/terraform/step_functions.tf`
    - `src/kr_vector_index/handlers/vector_index_handler.py`
  - Do not read:
    - Raw DynamoDB exports.
    - Large CloudWatch logs unless execution fails.
  - Optional read:
    - Focused Step Functions execution output if AWS CLI returns compact JSON.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-8-책임-분리`
- Must Read Before Implementation:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-8-책임-분리`
- Target Files:
  - `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_progress_20260630.md`
- Out of Scope:
  - Manual deletion or recreation of S3 Vector indexes.
  - Bypassing Step Functions with ad-hoc bulk write unless separately approved.
- Acceptance Criteria:
  - Step Functions execution is started only after explicit approval.
  - Execution input records target bucket/index and concurrency.
  - Execution ARN/id is recorded.
  - Planner output or execution event evidence shows `visitor_statistics` remains excluded.
- Verification:
  - `aws stepfunctions start-execution ...`
  - `aws stepfunctions describe-execution ...`
  - Record execution ARN, start time, input summary, and current status.

## Subtask 4: Monitor Batches And Retry Approved Failures

- Purpose: full rebuild 진행 중 batch 실패를 감시하고, 승인된 재시도 범위 안에서만 복구한다.
- Required Context:
  - Worker reports compact success/failure counts.
  - Repeated batch failures can indicate data, IAM, Bedrock, S3 Vector, or timeout issues.
- Context Budget:
  - Must read:
    - Step Functions execution status for the Task 8 execution ARN.
    - Compact failed batch output if present.
  - Do not read:
    - Full CloudWatch log streams unless failure diagnosis requires it.
  - Optional read:
    - Focused CloudWatch excerpts for failed batch IDs.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Must Read Before Implementation:
  - `#requirement-7-step-functions-map-기반-vector-분할`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Target Files:
  - `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_progress_20260630.md`
- Out of Scope:
  - Retrying failed batches with a different target index unless approved.
  - Increasing concurrency without approval.
- Acceptance Criteria:
  - Execution reaches `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `ABORTED`, or an explicitly reported partial status.
  - Failed batch IDs and failure reasons are recorded.
  - Retry decisions are recorded, including skipped retries.
  - Three repeated failures with the same mode stop the task and escalate.
- Verification:
  - `aws stepfunctions describe-execution ...`
  - `aws stepfunctions get-execution-history ...` with focused filtering or bounded output.
  - Focused CloudWatch reads only when needed.

## Subtask 5: Verify Full Rebuild Output And Protected Scope

- Purpose: 실제 rebuild 결과가 expected vector output과 protected data-plane boundary를 모두 만족하는지 확인한다.
- Required Context:
  - Task 9 final report will require visitor statistics, enrichment, protected data-plane, smoke, and rebuild evidence.
- Context Budget:
  - Must read:
    - `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`
    - `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_progress_20260630.md`
  - Do not read:
    - Full S3 object bodies unless manifest validation requires a focused read.
  - Optional read:
    - Manifest object metadata and compact manifest body.
    - Sample vector query response.
- Source of Truth:
  - Full Spec: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Required Sections:
  - `#requirement-3-visitor_statistics-coverage-보존-및-누락-보완-gate`
  - `#requirement-4-현재-브랜치-enrichment-field-loading-의도-보존`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Must Read Before Implementation:
  - `#requirement-3-visitor_statistics-coverage-보존-및-누락-보완-gate`
  - `#requirement-4-현재-브랜치-enrichment-field-loading-의도-보존`
  - `#requirement-9-검증-보고-및-운영-인수인계`
- Target Files:
  - `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_progress_20260630.md`
  - `docs/reports/TASK8_COMPLETION.md`
  - `docs/specs/TASK9_SUBTASKS.md`
  - `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`
- Out of Scope:
  - Writing the final Task 9 completion report in Task 8 unless explicitly requested.
- Acceptance Criteria:
  - Final vector counts are recorded, or failure/partial status is recorded with failed batch IDs.
  - Manifest path is recorded if aggregate ran.
  - Sample query evidence is recorded if rebuild succeeded.
  - `visitor_statistics` vector count remains `0`.
  - `visitor_statistics_rows`, city coverage, SK shape, `domain_sort_key` shape, and `gsi_sk` pollution evidence are preserved for Task 9.
  - Enrichment field counts and vector metadata enrichment rules are recorded without claiming enrichment-complete if live counts remain zero.
  - Protected DynamoDB/S3/S3 Vector delete/recreate remains absent.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m kr_vector_index.live_verification_cli`
  - Targeted vector count/query command approved for the active S3 Vector target.
  - Manifest read or metadata check if aggregate ran.
  - `git diff --check`

## Task 9 Evidence Carry-Forward

Task 8 completion must preserve the evidence required by `docs/specs/TASK9_COMPLETION_REPORT_TEMPLATE.md`.

At minimum, Task 8 must leave Task 9 with:

- full vector rebuild execution id and final status, or approved reason why it was not run;
- aggregate manifest path, or approved reason why aggregate was not run;
- final vector counts and sample query evidence if rebuild succeeded;
- `visitor_statistics` live row count, city coverage, residual city PKs, key shape, `gsi_sk` pollution check, and vector exclusion evidence;
- enrichment field counts, enrichment mode, vector metadata derived field counts, and full `metadata_enrichment` exclusion evidence;
- protected DynamoDB/S3/S3 Vector no-delete/no-recreate evidence;
- explicit user decisions and remaining risks.

After Task 8 completes, stop and create the required handover artifacts before Task 9 starts:

- User report: `docs/reports/TASK8_COMPLETION.md`
- Next-agent instruction sheet: `docs/specs/TASK9_SUBTASKS.md`
