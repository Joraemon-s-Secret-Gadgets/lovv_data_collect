# KR Enrichment Backfill Plan - 2026-06-30

## Summary

Subtask 10.2 prepares a bounded enrichment backfill plan for the current live state.

This task did not run a live enrichment backfill. It only refreshed read-only DynamoDB baseline evidence, ran a bounded dry-run, and defined approval gates, batch size, stop criteria, rollback boundaries, and verification commands.

Current recommendation:

- First approved live canary: `--limit 25`
- Expand only after canary verification passes.
- Do not claim enrichment-complete until non-zero successful rows are verified and vector metadata behavior is rechecked.

## Current Live Baseline

Read-only DynamoDB baseline refresh:

```json
{
  "attraction_rows": 7024,
  "metadata_enrichment": 0,
  "indoor_outdoor": 0,
  "vibe_tags": 0,
  "experience_tags": 0,
  "companion_fit": 0,
  "schema_version": 0
}
```

Live verifier:

```json
{
  "passed": true,
  "failures": [],
  "observations": {
    "visitor_statistics_rows": 2820,
    "visitor_statistics_coverage_ok": true,
    "enrichment_mode": "non-enrichment-complete"
  }
}
```

Interpretation:

- Backfill is still needed if enrichment-derived vector metadata is required.
- `visitor_statistics` remains healthy and is not part of the backfill.
- Current final reset report must remain `partial` until enrichment is actually written and verified.

## Existing Backfill Surface

Script:

```powershell
uv run python scripts\backfill_enrichment.py
```

Supported controls:

- `--dry-run`
- `--limit`
- `--city-pk`
- `--resume-after`
- `--table-name`
- `--region`
- `--profile`
- `--model-id`
- `--source-dataset`

Default parameters observed in dry-run:

```json
{
  "table_name": "TourKoreaDomainDataV2",
  "region": "us-east-1",
  "model_id": "openai.gpt-oss-120b-1:0",
  "prompt_version": "attraction-metadata-v2",
  "source_dataset": "raw/KR/details/20260625/"
}
```

Persistence behavior:

- On `succeeded`, the updater writes:
  - `metadata_enrichment`
  - `indoor_outdoor`
  - `vibe_tags`
  - `experience_tags`
  - `companion_fit`
  - `schema_version`
- On `failed` or `skipped`, it writes only `metadata_enrichment`.
- The runner stops after `MAX_CONSECUTIVE_FAILURES=3`.

## Dry-Run Verification

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python scripts\backfill_enrichment.py --dry-run --limit 25
```

Result:

```json
{
  "processed": 25,
  "planned_for_enrichment": 25,
  "skipped": 0,
  "failed": 0,
  "written": 0,
  "stopped_after_consecutive_failures": false,
  "resume_after": null
}
```

Interpretation:

- The first 25 candidate attractions are eligible for enrichment.
- Dry-run performed no Bedrock calls and no DynamoDB writes.
- This supports a first live canary size of 25 after explicit approval.

## Proposed Execution Plan

### Phase 0: Pre-Approval Gate

Do before any live write:

1. Re-run read-only baseline counts.
2. Re-run live verifier.
3. Confirm user approval for:
   - live Bedrock calls;
   - DynamoDB update writes to `TourKoreaDomainDataV2`;
   - first canary size;
   - stop criteria;
   - no vector rebuild until enrichment results are verified.

Commands:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
uv run python scripts\backfill_enrichment.py --dry-run --limit 25
```

### Phase 1: Live Canary

Recommended first live write, only after explicit approval:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python scripts\backfill_enrichment.py --limit 25
```

Expected success criteria:

- `processed=25`
- `written=25`
- `succeeded > 0`
- `failed=0` preferred for canary
- `stopped_after_consecutive_failures=false`
- live `metadata_enrichment` count increases above `0`
- at least one of the derived fields increases above `0`

If canary returns any `failed_items`, stop and inspect the error before expanding.

### Phase 2: Bounded Expansion

Only after Phase 1 passes:

Recommended expansion sizes:

1. `--limit 100`
2. `--limit 250`
3. city-scoped run with `--city-pk CITY#...` for high-priority cities

Do not jump directly to all `7024` attraction rows. Bedrock cost, throttling, and partial write behavior should be observed in bounded steps.

### Phase 3: Completion Verification

After each approved live batch:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Refresh DynamoDB counts:

```powershell
aws dynamodb query --region us-east-1 --table-name TourKoreaDomainDataV2 --index-name EntityTypeDomainIndex --select COUNT --key-condition-expression "entity_type = :e" --expression-attribute-values '{":e":{"S":"attraction"}}'
```

For each enrichment field, count `attribute_exists(field)` among attraction rows.

Also verify:

- `visitor_statistics_rows` remains `2820`.
- `visitor_statistics_coverage_ok=true`.
- no S3 Vector rebuild is started merely because enrichment rows now exist.
- final report continues to avoid `enrichment-complete` until coverage is intentionally defined and verified.

## Stop Criteria

Stop immediately if any of these occur:

- live verifier fails;
- `visitor_statistics_rows` drops below `2820`;
- `visitor_statistics_coverage_ok` is not `true`;
- canary has any DynamoDB `ClientError`;
- canary has any `MissingDynamoKeyError`;
- `failed_items` is non-empty in the first canary;
- `stopped_after_consecutive_failures=true`;
- three consecutive enrichment failures occur;
- Bedrock throttling repeats after retry/backoff at the script boundary;
- counts do not increase after a reported `written > 0`;
- unexpected fields are removed or clobbered in sampled records;
- user approval does not explicitly cover live writes and Bedrock calls.

## Rollback Boundary

No automatic rollback is approved in this plan.

Reason:

- The current script performs DynamoDB `UpdateItem` writes and does not capture before-images.
- Reverting enrichment fields safely would require a separately approved rollback plan with either DynamoDB PITR/export evidence or pre-write snapshots for the affected PK/SK set.

Before any live canary, recommended guard:

1. Capture the exact candidate PK/SK list for the approved bounded run.
2. For those PK/SK records, capture current enrichment field values.
3. Store the snapshot under a repo-ignored or approved artifact location before write.
4. Do not run rollback unless the user explicitly approves the rollback command and target keys.

For the first `--limit 25` canary, because current live enrichment counts are all `0`, a failed canary should normally be handled by stopping further expansion rather than attempting immediate rollback.

## Verification Commands

Read-only baseline:

```powershell
$fields = @('metadata_enrichment','indoor_outdoor','vibe_tags','experience_tags','companion_fit','schema_version')
aws dynamodb query --region us-east-1 --table-name TourKoreaDomainDataV2 --index-name EntityTypeDomainIndex --select COUNT --key-condition-expression 'entity_type = :e' --expression-attribute-values '{":e":{"S":"attraction"}}'
```

Dry-run:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python scripts\backfill_enrichment.py --dry-run --limit 25
```

Live canary, not approved by this report:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python scripts\backfill_enrichment.py --limit 25
```

Post-canary local tests:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m pytest src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrich_attraction.py src\kr_vector_index\tests\test_metadata.py --basetemp .cache\pytest-enrichment-backfill-plan -p no:cacheprovider
```

## Current Decision Needed

To execute any live backfill, the user must explicitly approve:

- Bedrock model calls;
- DynamoDB writes to `TourKoreaDomainDataV2`;
- first live canary size, recommended `25`;
- stop criteria above;
- no S3 Vector rebuild until enrichment write verification is complete.

This report is a plan only. It does not authorize execution.
