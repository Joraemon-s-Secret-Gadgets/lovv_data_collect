# KR Enrichment Failure Classification 125617 - 2026-06-30

Completion timestamp: 2026-06-30 20:17:22 +09:00

Responsible agent: Main Codex, Sequential Mode

## Summary

Task 12 classified the failed enrichment item from Task 11 and tested the next safe expansion gate.

Failed item:

- `PK=CITY#GANGNEUNG`
- `SK=ATTRACTION#125617`
- `content_id=125617`

Classification:

- Stored input fields are present and valid.
- Prompt length is `1576`, below the `MAX_PROMPT_LENGTH=12000` boundary.
- The failure matches the `json.loads(raw_text)` failure path in `src/kr_details_pipeline/enrichment_engine.py`.
- Best classification: malformed Bedrock response JSON, not malformed DynamoDB source data.

## Failed Item Evidence

Read-only DynamoDB `GetItem` and local prompt construction:

```json
{
  "field_lengths": {
    "PK": 14,
    "SK": 17,
    "address": 19,
    "closed_days": 4,
    "content_id": 6,
    "description": 416,
    "entity_type": 10,
    "experience_guide": 0,
    "opening_hours": 5,
    "parking": 0,
    "theme": 6,
    "theme_tags": 10,
    "title": 7
  },
  "field_presence": {
    "PK": true,
    "SK": true,
    "address": true,
    "closed_days": true,
    "content_id": true,
    "description": true,
    "entity_type": true,
    "experience_guide": false,
    "opening_hours": true,
    "parking": false,
    "theme": true,
    "theme_tags": true,
    "title": true
  },
  "identity": {
    "PK": "CITY#GANGNEUNG",
    "SK": "ATTRACTION#125617",
    "content_id": "125617",
    "entity_type": "attraction"
  },
  "input_hash": "sha256:b68eee10bb941ca7d3294768868ae066d3f217d1751d71fd06bf264551207d06",
  "metadata_enrichment": {
    "error_code": "validation_error",
    "failed_at": "2026-06-30T11:09:46Z",
    "status": "failed"
  },
  "prompt_length": 1576
}
```

ASCII-escaped value check showed normal Korean source strings. Examples:

- title: `제왕산/능경봉`
- theme: `자연·트레킹`
- address: `강원특별자치도 강릉시 성산면 어흘리`

## Parser Path

The live run printed:

```text
JSON parse error for item 125617: Expecting ':' delimiter: line 5 column 21 (char 212)
```

The matching code path:

- `enrich_attraction()` extracts the first text part from Bedrock `converse()`.
- It strips markdown fences if present.
- `json.loads(raw_text)` raises `JSONDecodeError`.
- The function returns `EnrichmentResult(status="failed", metadata_enrichment.error_code="validation_error")`.
- `update_attraction_enrichment()` persists failed metadata without top-level enrichment fields.

## Dry-Run Gate

### Direct next dry-run

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --dry-run --limit 500
```

Result:

```json
{
  "failed": 0,
  "failed_items": [],
  "planned_for_enrichment": 251,
  "processed": 500,
  "resume_after": null,
  "skipped": 249,
  "stopped_after_consecutive_failures": false,
  "succeeded": 0,
  "total_candidates": 500,
  "unchanged": 249,
  "written": 0
}
```

Interpretation:

- This would retry the failed item because `should_skip_enrichment()` only skips previous `status="succeeded"`.
- Direct live `--limit 500` was not used.

### Resumed dry-run

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --dry-run --limit 500 --resume-after ATTRACTION#125617
```

Result:

```json
{
  "failed": 0,
  "failed_items": [],
  "planned_for_enrichment": 461,
  "processed": 500,
  "resume_after": null,
  "skipped": 39,
  "stopped_after_consecutive_failures": false,
  "succeeded": 0,
  "total_candidates": 500,
  "unchanged": 39,
  "written": 0
}
```

Interpretation:

- This avoids retrying `ATTRACTION#125617`.
- It keeps the next live boundary bounded and avoids repeating the known failed item.

## Resumed Live Expansion

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --limit 500 --resume-after ATTRACTION#125617
```

Result:

```json
{
  "effective_parameters": {
    "city_pk": null,
    "dry_run": false,
    "limit": 500,
    "model_id": "openai.gpt-oss-120b-1:0",
    "profile": null,
    "prompt_version": "attraction-metadata-v2",
    "region": "us-east-1",
    "resume_after": "ATTRACTION#125617",
    "source_dataset": "raw/KR/details/20260625/",
    "table_name": "TourKoreaDomainDataV2"
  },
  "failed": 0,
  "failed_items": [],
  "planned_for_enrichment": 0,
  "processed": 500,
  "resume_after": null,
  "skipped": 39,
  "stopped_after_consecutive_failures": false,
  "succeeded": 461,
  "total_candidates": 500,
  "unchanged": 39,
  "written": 461
}
```

## Post-Run Verification

### DynamoDB counts

```json
{
  "attraction_rows": 7024,
  "companion_fit": 710,
  "experience_tags": 710,
  "indoor_outdoor": 710,
  "metadata_enrichment": 711,
  "schema_version": 710,
  "vibe_tags": 710
}
```

Interpretation:

- `metadata_enrichment=711` includes one failed metadata record.
- Top-level enrichment-derived fields are `710`.

### S3 Vector counts

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

### Live verifier

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

### Local tests

```text
46 passed in 0.37s
```

## Decision

Do not run another live expansion automatically in this Task.

Reason:

- The next larger run should use a fresh dry-run gate.
- The failed item is classified, but not retried.
- S3 Vector metadata remains stale and must stay as a separate explicit boundary.

Recommended next dry-run:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --dry-run --limit 1000 --resume-after ATTRACTION#125617
```

## Review

- Severity: Approved
- Area: Correctness
- Evidence: 실패 item은 정상 입력 필드를 가지고 있고 `json.loads(raw_text)` 실패 경로와 일치한다. resumed run은 실패 item을 건너뛰고 `failed=0`, `succeeded=461`로 완료됐다.
- Risk: `ATTRACTION#125617`은 아직 성공 enrichment가 아니며, full completion claim에서 제외해야 한다.
- Required Fix: 없음. 단일 retry 또는 parser hardening은 별도 Task로 분리한다.
- Retest: 단일 retry를 승인할 경우 해당 item만 대상으로 실행하고 DynamoDB field count를 다시 확인한다.

- Severity: Approved
- Area: Security
- Evidence: Task 12의 추가 live write는 DynamoDB enrichment update로 제한됐고 S3 Vector write/delete/recreate는 수행하지 않았다.
- Risk: 다음 batch부터는 Bedrock 비용과 실패 누적 위험이 커지므로 fresh dry-run gate가 필요하다.
- Required Fix: 없음.
- Retest: Task 13에서 `--dry-run --limit 1000 --resume-after ATTRACTION#125617`를 먼저 실행한다.
