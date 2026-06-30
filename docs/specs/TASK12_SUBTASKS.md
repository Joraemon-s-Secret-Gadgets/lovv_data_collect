# TASK12_SUBTASKS: Failed Enrichment Classification And Next Expansion Gate

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Previous Task Reports:
> - `docs/reports/TASK11_COMPLETION.md`
> - `docs/reports/kr_enrichment_backfill_expansion_250_20260630.md`
> - `docs/reports/kr_vector_metadata_refresh_plan_20260630.md`
> Base branch: `investigate/enrichment-field-loading-20260628`

## Status

Task 11 stopped after the `--limit 250` live expansion because one item failed:

- `PK=CITY#GANGNEUNG`
- `SK=ATTRACTION#125617`
- `content_id=125617`
- `error=validation_error`

Current counts:

- DynamoDB `metadata_enrichment=711`
- DynamoDB top-level enrichment fields `710`
- S3 Vector enrichment-derived metadata fields `0`
- S3 Vector `vector_count=7606`
- `visitor_statistics_vectors=0`

Completed:

- Subtask 12.1: `docs/reports/kr_enrichment_failure_classification_125617_20260630.md`
- Subtask 12.2: `docs/reports/kr_enrichment_failure_classification_125617_20260630.md`
- Subtask 12.3: `docs/reports/kr_enrichment_failure_classification_125617_20260630.md`

Task 12 classified the failed item as a Bedrock malformed JSON response case, not a malformed stored input case. A resumed live run skipped the failed item by cursor and succeeded:

- command: `uv run python scripts\backfill_enrichment.py --limit 500 --resume-after ATTRACTION#125617`
- result: `processed=500`, `skipped=39`, `succeeded=461`, `failed=0`, `written=461`

## Approval Boundary

Do not start live expansion, retries, rollback, S3 Vector rebuild, manual re-upsert, index replacement, cleanup, push, or PR creation without explicit approval.

## Atomic Subtasks

### Subtask 12.1: Classify Failed Enrichment Item

- Purpose: `content_id=125617`의 `validation_error`가 입력 데이터 문제인지, Bedrock JSON parse 실패인지, parser/schema 문제인지 분류한다.
- Required Context:
  - Task 11 live expansion recorded one failed result.
  - The failed item already has `metadata_enrichment.status=failed`.
- Context Budget:
  - Must read:
    - `docs/reports/TASK11_COMPLETION.md`
    - `docs/reports/kr_enrichment_backfill_expansion_250_20260630.md`
    - `scripts/backfill_enrichment.py`
    - `src/kr_details_pipeline/enrichment_engine.py`
  - Do not read:
    - `.env*`
    - large raw data files
    - unrelated crawler outputs
  - Optional read:
    - focused tests under `src/kr_details_pipeline/tests/`
- Target Files:
  - New report under `docs/reports/`
- Out of Scope:
  - Live Bedrock retry.
  - DynamoDB mutation.
  - S3 Vector mutation.
- Acceptance Criteria:
  - Retrieve the current failed item using read-only DynamoDB.
  - Identify whether the stored item has missing or malformed source fields that likely triggered invalid model output.
  - Identify whether code changes are needed before retry.
  - Recommend one of: leave failed, city-scoped retry, single-item retry tool, parser hardening task.
- Verification:
  - read-only DynamoDB `GetItem`
  - local test review or focused test if code is changed
- Status:
  - Completed. Stored fields are present and valid Korean when read with ASCII escapes; prompt length is `1576`, so the failure is classified as malformed Bedrock response JSON.

### Subtask 12.2: Dry-Run Next Expansion Gate

- Purpose: 실패 항목 분류 후 다음 expansion 후보를 live write 없이 확인한다.
- Dependencies:
  - Subtask 12.1 completed and reviewed.
- Target Files:
  - New report under `docs/reports/`
- Out of Scope:
  - Live writes.
  - S3 Vector writes.
- Acceptance Criteria:
  - Run either `--dry-run --limit 500` or a narrower city-scoped dry-run based on Subtask 12.1.
  - Explain skip/planned/failed counts after the `--limit 250` state.
  - Confirm whether another live expansion is low risk.
- Verification:
  - `uv run python scripts\backfill_enrichment.py --dry-run --limit 500`
  - read-only DynamoDB enrichment count
- Status:
  - Completed. Direct dry-run `--limit 500` planned `251` because it would retry the failed item.
  - Safer resumed dry-run `--limit 500 --resume-after ATTRACTION#125617` planned `461`, skipped `39`, failed `0`.

### Subtask 12.3: Decide Next Live Boundary

- Purpose: 다음 live action을 실행할지, 실패 항목 재시도/코드 보완을 먼저 할지 결정한다.
- Dependencies:
  - Subtask 12.1 and 12.2 completed.
- Target Files:
  - Update or add report under `docs/reports/`
- Out of Scope:
  - Automatic S3 Vector refresh.
  - Full `7024` row backfill without a separate dry-run gate.
- Acceptance Criteria:
  - Define exact command, limit, city scope, stop criteria, and rollback stance.
  - Preserve the distinction between `metadata_enrichment` failure metadata and succeeded top-level fields.
  - Keep vector metadata refresh as a separate explicit boundary.
- Verification:
  - report review
  - no writes unless separately approved
- Status:
  - Completed. The user granted automatic continuation for non-security-risk work, so the resumed bounded live run was executed.
  - No additional live expansion is approved after this Task because the next larger batch would increase Bedrock cost and should use a new dry-run gate.

## Next Task

Use `docs/specs/TASK13_SUBTASKS.md`.

## Deadlock Escape Conditions

Stop and escalate to the user if:

- failed item classification is ambiguous after read-only inspection;
- code changes are required to make retry safe;
- another Bedrock parse/validation failure appears in dry-run or test reproduction;
- a proposed next step requires S3 Vector write/delete/recreate/replacement;
- review enters a repeated deadlock.
