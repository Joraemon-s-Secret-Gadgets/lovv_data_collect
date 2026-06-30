# KR Enrichment Backfill Canary Report - 2026-06-30

Completion timestamp: 2026-06-30 19:52:10 +09:00

Responsible agent: Main Codex, Sequential Mode

## Summary

This report records the bounded live enrichment backfill canary selected after comparing the remaining follow-up paths.

Decision:

- Do not run vector count discrepancy remediation now.
- Do not delete, recreate, replace, or manually re-upsert the S3 Vector index.
- Run only the first bounded enrichment canary recommended by `docs/reports/kr_enrichment_backfill_plan_20260630.md`: `--limit 25`.

Rationale:

- `docs/reports/kr_vector_count_discrepancy_analysis_20260630.md` classifies the `7662` aggregate writes vs `7606` current unique vectors as duplicate-key/upsert replacement behavior. Remediation would require a separately approved source-side duplicate audit or vector rewrite path.
- The enrichment backfill path has a bounded canary with explicit stop criteria and no S3 Vector write.

## Commands And Results

### Baseline verifier

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
    "enrichment_mode": "non-enrichment-complete"
  }
}
```

### Dry-run gate

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --limit 25 --dry-run
```

Result:

```json
{
  "effective_parameters": {
    "city_pk": null,
    "dry_run": true,
    "limit": 25,
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
  "planned_for_enrichment": 25,
  "processed": 25,
  "resume_after": null,
  "skipped": 0,
  "stopped_after_consecutive_failures": false,
  "succeeded": 0,
  "total_candidates": 25,
  "unchanged": 0,
  "written": 0
}
```

### Live canary

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python scripts\backfill_enrichment.py --limit 25
```

Result:

```json
{
  "effective_parameters": {
    "city_pk": null,
    "dry_run": false,
    "limit": 25,
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
  "planned_for_enrichment": 0,
  "processed": 25,
  "resume_after": null,
  "skipped": 0,
  "stopped_after_consecutive_failures": false,
  "succeeded": 25,
  "total_candidates": 25,
  "unchanged": 0,
  "written": 25
}
```

### Post-canary live verifier

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

Interpretation:

- The verifier accepts both `enrichment-complete` and `non-enrichment-complete` as valid modes.
- This does not mean all `7024` attraction rows were enriched.
- The field count scan below is the precise canary completion evidence.

### DynamoDB field count

Read-only count over `TourKoreaDomainDataV2` attraction items through `EntityTypeDomainIndex`:

```json
{
  "attraction_rows": 7024,
  "companion_fit": 25,
  "experience_tags": 25,
  "indoor_outdoor": 25,
  "metadata_enrichment": 25,
  "schema_version": 25,
  "vibe_tags": 25
}
```

### S3 Vector field count

Read-only paginated list over `lovv-vector-dev` / `kr-tour-domain-v2` with metadata returned:

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

- DynamoDB enrichment canary succeeded.
- Existing S3 Vector metadata is not refreshed by the DynamoDB-only backfill.
- The vector inventory remains `7606` unique vectors with `visitor_statistics_vectors=0`.

### Local tests

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python -m pytest src\kr_details_pipeline\tests\test_enrichment_persistence.py src\kr_details_pipeline\tests\test_backfill_enrichment.py src\kr_details_pipeline\tests\test_enrich_attraction.py src\kr_vector_index\tests\test_metadata.py --basetemp .cache\pytest-enrichment-backfill-live -p no:cacheprovider
```

Result:

```text
46 passed in 0.39s
```

## Spec Alignment Checklist

- [x] Bounded size: live run used `--limit 25`.
- [x] Stop criteria: no failed items, no consecutive failure stop.
- [x] No vector rebuild: no Step Functions rebuild, S3 Vector rewrite, or index replacement was run.
- [x] DynamoDB verification: enrichment-derived fields increased from `0` to `25`.
- [x] S3 Vector verification: metadata-derived fields remain `0`, so vector metadata completeness is not claimed.
- [x] Visitor statistics invariant: `visitor_statistics_rows=2820`, coverage OK, and `visitor_statistics_vectors=0`.

## Changed Files

- `docs/specs/TASK10_SUBTASKS.md`
- `docs/reports/kr_enrichment_backfill_canary_20260630.md`
- `docs/reports/TASK10_COMPLETION.md`
- `docs/specs/TASK11_SUBTASKS.md`

## Remaining Risks

- Only the first 25 attraction rows were enriched. The full `7024` attraction-row backfill is not complete.
- S3 Vector metadata remains stale relative to the newly enriched DynamoDB rows.
- The `7662` write count vs `7606` unique vector count discrepancy is not remediated.
- No rollback was run or approved. A rollback would need key-level before-images or a separately approved DynamoDB rollback plan.

## Recommended Next Action

Use `docs/specs/TASK11_SUBTASKS.md`.

Recommended order:

1. Expand DynamoDB enrichment backfill from 25 to 250 only after re-reading this report.
2. Continue bounded batches only while `failed=0` or failures are understood and explicitly accepted.
3. Decide separately whether to refresh vector metadata after DynamoDB enrichment reaches the chosen completion threshold.
