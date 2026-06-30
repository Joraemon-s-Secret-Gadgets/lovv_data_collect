# TASK13_SUBTASKS: Next Enrichment Expansion Gate After Resumed Run

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Previous Task Reports:
> - `docs/reports/TASK12_COMPLETION.md`
> - `docs/reports/kr_enrichment_failure_classification_125617_20260630.md`
> Base branch: `investigate/enrichment-field-loading-20260628`

## Status

Task 12 completed a resumed live expansion that skipped the known failed item:

- command: `uv run python scripts\backfill_enrichment.py --limit 500 --resume-after ATTRACTION#125617`
- result: `processed=500`, `skipped=39`, `succeeded=461`, `failed=0`, `written=461`

Current counts:

- DynamoDB `metadata_enrichment=711`
- DynamoDB top-level enrichment fields `710`
- known failed enrichment item: `ATTRACTION#125617`
- S3 Vector enrichment-derived metadata fields `0`
- S3 Vector `vector_count=7606`
- `visitor_statistics_vectors=0`

## Approval Boundary

Do not start live expansion, failed-item retry, rollback, S3 Vector rebuild, manual re-upsert, index replacement, cleanup, push, or PR creation without explicit approval.

The user has allowed automatic continuation only where the agent judges the action not security-risky. For this Task, the first automatic step may be the dry-run gate. Live expansion should be run only if the dry-run has no failed items and the projected Bedrock cost remains bounded.

## Atomic Subtasks

### Subtask 13.1: Dry-Run Expansion To 1000 After Failed Cursor

- Purpose: 다음 live expansion 전에 `--resume-after ATTRACTION#125617 --limit 1000` 경계의 skip/planned/failure 상태를 read-only로 확인한다.
- Required Context:
  - Task 12 succeeded with resumed `--limit 500`.
  - The known failed item remains failed and should not be retried by default.
- Context Budget:
  - Must read:
    - `docs/reports/TASK12_COMPLETION.md`
    - `docs/reports/kr_enrichment_failure_classification_125617_20260630.md`
    - `scripts/backfill_enrichment.py`
  - Do not read:
    - `.env*`
    - large raw data files
    - unrelated crawler outputs
- Target Files:
  - New report under `docs/reports/`
- Out of Scope:
  - Live writes.
  - Failed item retry.
  - S3 Vector writes.
- Acceptance Criteria:
  - Dry-run completes with `failed=0`.
  - Result explains how many rows are skipped and how many are newly planned after Task 12.
  - DynamoDB current enrichment counts are refreshed read-only.
- Verification:
  - `uv run python scripts\backfill_enrichment.py --dry-run --limit 1000 --resume-after ATTRACTION#125617`
  - read-only DynamoDB enrichment count

### Subtask 13.2: Decide Or Run Live Expansion To 1000

- Purpose: Subtask 13.1 결과가 안전하면 bounded live expansion을 실행하거나, 비용/실패 위험 때문에 명시적으로 보류한다.
- Dependencies:
  - Subtask 13.1 completed and reviewed.
- Target Files:
  - Update or add report under `docs/reports/`
- Out of Scope:
  - Failed item retry.
  - S3 Vector refresh.
  - Full `7024` row backfill without additional gates.
- Acceptance Criteria:
  - If live run proceeds, exact command and result are recorded.
  - If live run is deferred, reason is recorded.
  - Stop immediately on `failed_items` non-empty, throttling, 429, or consecutive failure stop.
- Verification:
  - live command result if executed
  - read-only DynamoDB count
  - focused pytest command

### Subtask 13.3: Refresh Next Vector Boundary Decision

- Purpose: DynamoDB enrichment count가 증가한 이후에도 S3 Vector metadata refresh를 계속 분리할지 판단한다.
- Dependencies:
  - Subtask 13.2 completed.
- Target Files:
  - Report under `docs/reports/`
- Out of Scope:
  - Running vector writes.
- Acceptance Criteria:
  - S3 Vector metadata count is refreshed read-only.
  - The known `7662` aggregate vs `7606` unique count risk is preserved.
  - Next vector write path is not auto-executed.
- Verification:
  - read-only S3 Vector paginated count
  - no writes

## Deadlock Escape Conditions

Stop and escalate to the user if:

- dry-run shows failed items;
- live run returns any failed item;
- Bedrock throttling or 429 appears;
- DynamoDB count does not increase after `written > 0`;
- next live scope would exceed a bounded batch without a dry-run gate;
- S3 Vector refresh requires put/delete/recreate/replacement;
- review enters a repeated deadlock.
