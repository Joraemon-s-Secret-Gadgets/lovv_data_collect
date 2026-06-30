# TASK10_SUBTASKS: Follow-Up Boundary After KR Lambda/SFN Reset

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Previous Task Reports:
> - `docs/reports/TASK7_COMPLETION.md`
> - `docs/reports/TASK8_COMPLETION.md`
> - `docs/reports/TASK9_COMPLETION.md`
> Final Evidence Report: `docs/reports/kr_lambda_sfn_batch_reset_completion_20260630.md`
> Base branch: `investigate/enrichment-field-loading-20260628`

## Status

Task 10 follow-up execution is proceeding one approved Subtask at a time.

Completed:

- Subtask 10.1: `docs/reports/kr_vector_count_discrepancy_analysis_20260630.md`
- Subtask 10.2: `docs/reports/kr_enrichment_backfill_plan_20260630.md`

Task 9 completed the final report and formal review. The final report status remains `partial` because:

- aggregate/manifest reports `vector_success_count=7662`;
- current S3 Vector unique count is `7606`;
- live enrichment-derived field counts remain `0`;
- enrichment-complete vector output cannot be claimed.

## Approval Boundary

Do not start any follow-up work without explicit user approval.

Not approved:

- S3 Vector index delete/recreate/replacement
- another full vector rebuild
- manual vector re-upsert
- vector count discrepancy remediation
- enrichment backfill
- cleanup
- commit
- PR creation

## Candidate Follow-Up Subtasks

### Subtask 10.1: Analyze Vector Count Discrepancy

- Purpose: `7662` aggregate successful writes와 `7606` current unique vectors 차이의 원인을 분류한다.
- Target Files:
  - New report under `docs/reports/`
- Out of Scope:
  - Any vector writes, deletes, or rebuilds.
- Acceptance Criteria:
  - Explain whether the delta is caused by duplicate keys, upsert replacement, list semantics, stale replacement, or another verified cause.
  - Preserve `visitor_statistics_vectors=0` as a separate invariant.
- Verification:
  - Read-only S3 Vector list/query operations only.

### Subtask 10.2: Plan Enrichment Backfill

- Purpose: live enrichment-derived counts `0` 상태를 보완하기 위한 bounded backfill 계획을 작성한다.
- Target Files:
  - New spec or report under `docs/`
- Out of Scope:
  - Running the backfill without separate approval.
- Acceptance Criteria:
  - Define bounded size, rollback/stop criteria, and verification commands.
  - Do not claim enrichment-complete before non-zero succeeded rows are verified.
- Verification:
  - Read-only DynamoDB baseline refresh.
- Status:
  - Completed as plan only at `docs/reports/kr_enrichment_backfill_plan_20260630.md`.
  - Live backfill execution remains unapproved.

### Subtask 10.3: Commit Or Publish Current Work

- Purpose: current Task 7-9 artifacts and Terraform changes를 Conventional Commit 또는 PR로 정리한다.
- Target Files:
  - Git metadata only after explicit approval.
- Out of Scope:
  - Source changes unrelated to current Task 7-9 scope.
- Acceptance Criteria:
  - `.env*` files remain untracked.
  - Commit message follows project convention.
  - PR, if requested, uses the user-approved base/target branch.
- Verification:
  - `git status --short`
  - staged diff review

## Stop Boundary

Stop until the user chooses a specific follow-up. Do not infer approval from this file.
