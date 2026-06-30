# KR Enrichment Backfill Expansion 250 Report - 2026-06-30

Completion timestamp: 2026-06-30 20:14:11 +09:00

Responsible agent: Main Codex, Sequential Mode

## Summary

Task 11 expanded the enrichment backfill from the Task 10 canary boundary to `--limit 250`.

Outcome:

- Dry-run passed.
- Live expansion completed with one failed enrichment result.
- No further live expansion was run.
- No S3 Vector write, rebuild, delete/recreate, replacement, or manual re-upsert was run.

## Decision

Automatic continuation is stopped after this run.

Reason:

- The live command returned `failed=1`.
- The failed item is `CITY#GANGNEUNG` / `ATTRACTION#125617`, `content_id=125617`.
- The failure is persisted as `metadata_enrichment.status=failed` with `error_code=validation_error`.
- Expanding beyond `--limit 250` before classifying this validation failure would violate the Task 11 stop criteria.

## Commands And Results

### Subtask 11.1 dry-run

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --dry-run --limit 250
```

Result:

```json
{
  "effective_parameters": {
    "city_pk": null,
    "dry_run": true,
    "limit": 250,
    "model_id": "openai.gpt-oss-120b-1:0",
    "profile": null,
    "prompt_version": "attraction-metadata-v2",
    "region": "us-east-1",
    "resume_after": null,
    "source_dataset": "raw/KR/details/20260625/",
    "table_name": "TourKoreaDomainDataV2"
  },
  "failed": 0,
  "failed_items": [],
  "planned_for_enrichment": 225,
  "processed": 250,
  "resume_after": null,
  "skipped": 25,
  "stopped_after_consecutive_failures": false,
  "succeeded": 0,
  "total_candidates": 250,
  "unchanged": 25,
  "written": 0
}
```

Interpretation:

- The first 25 rows from Task 10 canary were skipped as expected.
- The next 225 rows were planned for enrichment.
- There were no dry-run failures or stop signals.

### Subtask 11.2 live expansion

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --limit 250
```

Observed stderr/stdout during run:

```text
JSON parse error for item 125617: Expecting ':' delimiter: line 5 column 21 (char 212)
```

Final result:

```json
{
  "effective_parameters": {
    "city_pk": null,
    "dry_run": false,
    "limit": 250,
    "model_id": "openai.gpt-oss-120b-1:0",
    "profile": null,
    "prompt_version": "attraction-metadata-v2",
    "region": "us-east-1",
    "resume_after": null,
    "source_dataset": "raw/KR/details/20260625/",
    "table_name": "TourKoreaDomainDataV2"
  },
  "failed": 1,
  "failed_items": [
    {
      "PK": "CITY#GANGNEUNG",
      "SK": "ATTRACTION#125617",
      "content_id": "125617",
      "error": "validation_error"
    }
  ],
  "planned_for_enrichment": 0,
  "processed": 250,
  "resume_after": null,
  "skipped": 25,
  "stopped_after_consecutive_failures": false,
  "succeeded": 224,
  "total_candidates": 250,
  "unchanged": 25,
  "written": 225
}
```

Interpretation:

- `written=225` includes the failed result metadata write.
- `succeeded=224` produced top-level enrichment-derived fields.
- `failed=1` produced only failed `metadata_enrichment`.
- `stopped_after_consecutive_failures=false`, but further expansion is still stopped because `failed_items` is non-empty.

## Post-Run Verification

### Live verifier

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python -m kr_vector_index.live_verification_cli
```

Result:

```json
{
  "passed": true,
  "failures": [],
  "observations": {
    "visitor_statistics_rows": 2820,
    "visitor_statistics_coverage_ok": true,
    "enrichment_mode": "enrichment-complete"
  }
}
```

### DynamoDB enrichment field counts

Read-only count over `TourKoreaDomainDataV2` attraction items:

```json
{
  "attraction_rows": 7024,
  "companion_fit": 249,
  "experience_tags": 249,
  "indoor_outdoor": 249,
  "metadata_enrichment": 250,
  "schema_version": 249,
  "vibe_tags": 249
}
```

Interpretation:

- `metadata_enrichment=250` because the failed item records failure metadata.
- Top-level fields are `249` because only succeeded enrichment writes those fields.

### Failed item read

Read-only `GetItem` for `CITY#GANGNEUNG` / `ATTRACTION#125617`:

```json
{
  "PK": "CITY#GANGNEUNG",
  "SK": "ATTRACTION#125617",
  "content_id": "125617",
  "metadata_enrichment": {
    "error_code": "validation_error",
    "failed_at": "2026-06-30T11:09:46Z",
    "status": "failed"
  }
}
```

### S3 Vector metadata count

Read-only paginated list over `lovv-vector-dev` / `kr-tour-domain-v2`:

```json
{
  "companion_fit": 0,
  "experience_tags": 0,
  "indoor_outdoor": 0,
  "metadata_enrichment": 0,
  "metadata_entity_counts": {
    "attraction": 6973,
    "city": 240,
    "festival": 393
  },
  "pages": 16,
  "schema_version": 0,
  "vector_count": 7606,
  "vibe_tags": 0,
  "visitor_statistics_vectors": 0
}
```

Interpretation:

- DynamoDB enrichment expansion does not refresh existing S3 Vector metadata.
- `visitor_statistics_vectors=0` remains preserved.
- Current unique vector inventory remains `7606`.

### Local tests

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python -m pytest src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrich_attraction.py src\kr_vector_index\tests\test_metadata.py --basetemp .cache\pytest-enrichment-task11 -p no:cacheprovider
```

Result:

```text
46 passed in 0.51s
```

## Security And Safety Review

- Severity: Approved
- Area: External API
- Evidence: live 확장은 `--limit 250`으로 제한됐고, dry-run 통과 후 한 번만 실행됐다. Bedrock 호출 중 한 항목이 validation error로 실패했지만 연속 실패 stop은 발생하지 않았다.
- Risk: 실패 항목을 분류하지 않고 추가 확장하면 같은 validation failure가 반복되거나 비용이 누적될 수 있다.
- Required Fix: 추가 확장 전에 `content_id=125617`의 입력과 Bedrock 응답 parse 실패 원인을 분류한다.
- Retest: 실패 원인 분류 후 `--dry-run --limit 500` 또는 city-scoped run을 먼저 확인한다.

- Severity: Approved
- Area: Data Storage
- Evidence: DynamoDB writes는 enrichment fields update로 제한됐고, S3 Vector write/delete/recreate는 실행하지 않았다.
- Risk: `metadata_enrichment=250`과 top-level enrichment fields `249`가 서로 다른 것은 실패 metadata가 기록됐기 때문이다. 이를 전체 성공으로 해석하면 안 된다.
- Required Fix: 없음. 단, 다음 보고서에서는 succeeded rows와 failed metadata rows를 분리해서 집계한다.
- Retest: read-only DynamoDB count와 failed item GetItem을 재실행한다.

## Stop Boundary

Do not continue to `--limit 500`, full backfill, city-scoped retries, rollback, or vector refresh until the failed item is classified and the user confirms the next bounded action.
