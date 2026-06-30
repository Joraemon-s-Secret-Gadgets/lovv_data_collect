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
- Subtask 10.3: local Conventional Commit `d63596c fix(kr-reset): complete vector rebuild reset workflow`
- Subtask 10.4: `docs/reports/kr_enrichment_backfill_canary_20260630.md`

Task 9 completed the final report and formal review. Subtask 10.4 changed the live DynamoDB enrichment baseline from zero to a bounded canary result:

- aggregate/manifest reports `vector_success_count=7662`;
- current S3 Vector unique count is `7606`;
- live DynamoDB enrichment-derived field counts are now `25` for `metadata_enrichment`, `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, and `schema_version`;
- current S3 Vector metadata-derived field counts remain `0`, so enrichment-complete vector output still cannot be claimed.

## Approval Boundary

Do not start any follow-up work without explicit user approval.

Not approved:

- S3 Vector index delete/recreate/replacement
- another full vector rebuild
- manual vector re-upsert
- vector count discrepancy remediation
- enrichment backfill expansion beyond the completed `--limit 25` canary
- cleanup
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
- Status:
  - Completed by local commit `d63596c`.

### Subtask 10.4: Run Bounded Enrichment Backfill Canary

- Purpose: live enrichment-derived counts `0` 상태를 완화하기 위해 first approved live canary `--limit 25`를 실행하고 DynamoDB/S3 Vector evidence를 분리해 기록한다.
- Target Files:
  - `docs/reports/kr_enrichment_backfill_canary_20260630.md`
- Out of Scope:
  - Full enrichment backfill expansion.
  - S3 Vector rebuild, re-upsert, index replacement, or vector count discrepancy remediation.
  - Rollback.
- Acceptance Criteria:
  - Dry-run `--limit 25` passes before live run.
  - Live canary reports `written=25`, `succeeded=25`, `failed=0`, and `stopped_after_consecutive_failures=false`.
  - Live DynamoDB enrichment-derived counts increase above `0`.
  - S3 Vector metadata-derived counts are checked separately and not claimed as refreshed unless they are actually non-zero.
- Verification:
  - `uv run python scripts\backfill_enrichment.py --limit 25 --dry-run`
  - `uv run python scripts\backfill_enrichment.py --limit 25`
  - DynamoDB count scan for enrichment-derived fields
  - read-only S3 Vector paginated count
  - focused pytest enrichment/vector metadata tests
- Status:
  - Completed at `docs/reports/kr_enrichment_backfill_canary_20260630.md`.

## Stop Boundary

Stop until the user chooses a specific follow-up. Do not infer approval from this file.

Recommended next Task:

- `docs/specs/TASK11_SUBTASKS.md` for expansion from canary to bounded batches and, only after DynamoDB verification, a separately approved vector metadata refresh path.
