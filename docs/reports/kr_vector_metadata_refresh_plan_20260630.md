# KR Vector Metadata Refresh Plan - 2026-06-30

Completion timestamp: 2026-06-30 20:14:11 +09:00

Responsible agent: Main Codex, Sequential Mode

## Summary

Task 11.3 evaluated whether the existing S3 Vector metadata should be refreshed after DynamoDB enrichment expansion.

Decision:

- Do not run automatic S3 Vector refresh now.
- Do not run Step Functions vector-only rebuild now.
- Do not manually re-upsert vectors now.
- Do not delete, recreate, replace, or migrate the S3 Vector index now.

Reason:

- The `--limit 250` enrichment expansion produced one failed item.
- S3 Vector inventory already has a known aggregate-vs-unique discrepancy: `7662` aggregate writes vs `7606` current unique vectors.
- Any vector refresh is a live S3 Vector write path and should be separated from the enrichment backfill failure classification.

## Current Evidence

### DynamoDB

Current attraction enrichment-derived counts:

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

Failed enrichment item:

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

### S3 Vector

Current S3 Vector inventory:

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

Known discrepancy from `docs/reports/kr_vector_count_discrepancy_analysis_20260630.md`:

- aggregate/manifest `vector_success_count=7662`
- current unique vector count `7606`
- best classification: duplicate vector keys causing S3 Vector upsert replacement

## Option Comparison

| Option | Writes? | Benefit | Risk | Recommendation |
| --- | --- | --- | --- | --- |
| No vector refresh yet | No | Preserves current stable vector index while DynamoDB backfill failure is classified | Vector metadata remains stale | Recommended now |
| City-scoped vector worker rerun | Yes, S3 Vector upsert | Smallest write scope if limited to one or a few `CITY#...` partitions | Requires exact affected cities and can still overwrite duplicate keys | Candidate after failure classification |
| Bounded Step Functions vector-only rerun | Yes, S3 Vector upsert and manifest write | Uses existing planner/worker/aggregator path | Could touch more cities than intended and repeats aggregate-vs-unique ambiguity | Not automatic |
| Full vector rebuild | Yes, large S3 Vector upsert and manifest write | Refreshes all vector metadata from current DynamoDB | Expensive, repeats known `7662` vs `7606` issue, and includes one failed enrichment row | Reject until backfill is healthier |
| New dated index and cutover | Yes, creates/populates new index, routing/cutover needed | Safest rollback story if full refresh is needed | More infra/routing work and requires explicit cutover plan | Best for production-grade refresh, but requires a new Spec/Task |

## Recommended Path

1. Classify the failed item `content_id=125617`.
2. Decide whether failed enrichment metadata should remain as-is, be retried city-scoped, or be normalized as an accepted failed row.
3. Continue DynamoDB backfill only in bounded batches after the failure decision.
4. Refresh S3 Vector metadata only after DynamoDB enrichment reaches a chosen threshold and failed rows are explicitly handled.
5. Prefer a new dated S3 Vector index if full metadata refresh is required and rollback matters.

## Verification Boundary For Any Future Vector Refresh

Before a future vector write:

- read-only DynamoDB enrichment count;
- read-only S3 Vector inventory count;
- source-side duplicate vector key audit;
- target bucket/index confirmation;
- explicit write scope;
- rollback/cutover decision;
- no `.env*` staging or secret exposure.

After a future vector write:

- S3 Vector paginated list count;
- enrichment-derived metadata counts in vector metadata;
- `visitor_statistics_vectors=0`;
- sample query with returned metadata;
- manifest count vs unique vector count comparison;
- focused vector tests.

## Review

- Severity: Approved
- Area: Spec Alignment
- Evidence: Task 11.3 required comparing no refresh, city-scoped worker rerun, bounded vector-only rerun, full rebuild, and dated-index cutover. All options are compared above with cost/risk boundaries.
- Risk: Running refresh automatically now would mix a partially failed enrichment batch with an S3 Vector write path and obscure whether vector metadata reflects succeeded rows only.
- Required Fix: 없음. Vector refresh remains a separate approval boundary.
- Retest: Before any vector write, re-run read-only DynamoDB/S3 Vector counts and duplicate-key audit.

- Severity: Approved
- Area: Security
- Evidence: This Task performed read-only vector verification and did not run S3 Vector put/delete/recreate operations.
- Risk: Future vector writes can alter retrieval behavior and should not be treated as low-risk automation while failed enrichment rows and duplicate key behavior remain unresolved.
- Required Fix: 없음.
- Retest: Future Task must include explicit target bucket/index and rollback/cutover verification.
