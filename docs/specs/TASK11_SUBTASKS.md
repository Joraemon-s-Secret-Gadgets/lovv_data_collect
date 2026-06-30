# TASK11_SUBTASKS: Bounded Enrichment Expansion And Vector Metadata Refresh Boundary

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Previous Task Reports:
> - `docs/reports/TASK10_COMPLETION.md`
> - `docs/reports/kr_enrichment_backfill_canary_20260630.md`
> - `docs/reports/kr_enrichment_backfill_plan_20260630.md`
> - `docs/reports/kr_vector_count_discrepancy_analysis_20260630.md`
> Base branch: `investigate/enrichment-field-loading-20260628`

## Status

Task 10 completed a first live enrichment backfill canary:

- DynamoDB attraction rows: `7024`
- DynamoDB enrichment-derived field counts: `25`
- S3 Vector current unique vectors: `7606`
- S3 Vector enrichment-derived metadata counts: `0`
- `visitor_statistics_vectors=0`

Task 11 must continue one approved Subtask at a time.

Completed:

- Subtask 11.1: `docs/reports/kr_enrichment_backfill_expansion_250_20260630.md`
- Subtask 11.2: `docs/reports/kr_enrichment_backfill_expansion_250_20260630.md`
- Subtask 11.3: `docs/reports/kr_vector_metadata_refresh_plan_20260630.md`

Task 11 stopped further live expansion because the `--limit 250` run produced one failed enrichment result:

- failed item: `CITY#GANGNEUNG` / `ATTRACTION#125617`
- `content_id=125617`
- error: `validation_error`
- current DynamoDB enrichment-derived field counts: `metadata_enrichment=250`; top-level enrichment fields `249`

## Approval Boundary

Do not start any live write or vector refresh without explicit approval.

Not approved by this file:

- live enrichment expansion beyond the completed `--limit 250` run
- S3 Vector rebuild, manual re-upsert, delete/recreate, replacement, or index migration
- rollback
- cleanup
- PR creation

## Atomic Subtasks

### Subtask 11.1: Dry-Run Expansion To 250

- Purpose: `--limit 250` live 확장 전에 현재 skip/write 후보와 stop risk를 read-only로 확인한다.
- Required Context:
  - Task 10 canary succeeded for 25 rows.
  - DynamoDB enrichment counts are now 25, so the first 25 rows should normally be skipped on subsequent runs.
- Context Budget:
  - Must read:
    - `docs/reports/TASK10_COMPLETION.md`
    - `docs/reports/kr_enrichment_backfill_canary_20260630.md`
    - `scripts/backfill_enrichment.py`
  - Do not read:
    - `.env*`
    - large raw data files
    - `.git` internals
  - Optional read:
    - `docs/reports/kr_enrichment_backfill_plan_20260630.md`
- Source of Truth:
  - `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
- Target Files:
  - New report under `docs/reports/`
- Out of Scope:
  - Live writes.
  - Vector rebuild or re-upsert.
- Acceptance Criteria:
  - `uv run python scripts\backfill_enrichment.py --dry-run --limit 250` completes.
  - The result explains processed, skipped, planned, and failed counts after the 25-row canary.
  - No DynamoDB or S3 Vector mutation is performed.
- Verification:
  - `git status --short`
  - dry-run command output
  - read-only DynamoDB field count
- Status:
  - Completed. Dry-run processed `250`, skipped `25`, planned `225`, failed `0`, written `0`.

### Subtask 11.2: Live Expansion To 250

- Purpose: Subtask 11.1 dry-run이 통과한 경우에만 live enrichment backfill을 `--limit 250`으로 확장한다.
- Dependencies:
  - Subtask 11.1 completed and reviewed.
  - User approval after reviewing Subtask 11.1 result.
- Target Files:
  - New report under `docs/reports/`
- Out of Scope:
  - Full `7024` row backfill.
  - S3 Vector write, rebuild, delete/recreate, or manual re-upsert.
  - Rollback.
- Acceptance Criteria:
  - Live run completes without `stopped_after_consecutive_failures=true`.
  - `failed_items` is empty, or each failure is classified before any further expansion.
  - DynamoDB enrichment-derived counts increase above the Task 10 canary baseline of `25`.
  - S3 Vector metadata remains explicitly checked and not claimed refreshed unless a vector write path runs.
- Verification:
  - `uv run python scripts\backfill_enrichment.py --limit 250`
  - read-only DynamoDB field count
  - read-only S3 Vector paginated metadata count
  - focused pytest command from Task 10 canary report
- Status:
  - Completed with `failed=1`.
  - Live run processed `250`, skipped `25`, wrote `225`, succeeded `224`, and recorded one failed result.
  - No further expansion is approved until the failed item is reviewed.

### Subtask 11.3: Plan Vector Metadata Refresh

- Purpose: DynamoDB enrichment expansion 이후 S3 Vector metadata를 새로 반영할 안전한 방법을 결정한다.
- Dependencies:
  - Subtask 11.2 completed and reviewed, or user explicitly decides to plan before expansion.
- Target Files:
  - New plan/report under `docs/reports/` or `docs/specs/`
- Out of Scope:
  - Running Step Functions full rebuild.
  - Manual vector re-upsert.
  - S3 Vector index delete/recreate/replacement.
- Acceptance Criteria:
  - Compare at least these options:
    - no vector refresh yet;
    - city-scoped vector worker rerun;
    - bounded Step Functions vector-only rerun;
    - full vector rebuild;
    - new dated index and cutover.
  - Include current `7662` aggregate writes vs `7606` unique vectors risk.
  - Include cost, rollback, and verification boundary.
- Verification:
  - read-only S3 Vector count
  - read-only DynamoDB enrichment count
  - no writes
- Status:
  - Completed at `docs/reports/kr_vector_metadata_refresh_plan_20260630.md`.
  - Automatic vector refresh was rejected for now because it would require an explicit S3 Vector write path while one enrichment failure and the unique-vector discrepancy remain unresolved.

## Next Task

Use `docs/specs/TASK12_SUBTASKS.md`.

## Deadlock Escape Conditions

Stop and escalate to the user if:

- dry-run or live run fails three consecutive times;
- `failed_items` is non-empty and the error class is unclear;
- Bedrock throttling or 429 appears;
- DynamoDB counts do not increase after `written > 0`;
- vector metadata refresh would require delete/recreate/replacement;
- review enters a repeated deadlock.
