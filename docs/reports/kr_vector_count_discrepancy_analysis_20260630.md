# KR Vector Count Discrepancy Analysis - 2026-06-30

## Summary

Subtask 10.1 analyzed the difference between:

- aggregate/manifest `vector_success_count=7662`
- current S3 Vector unique list count `7606`

Conclusion:

- The discrepancy is best classified as cross-batch duplicate vector keys causing S3 Vector upsert replacement.
- The verified mechanism is in the code path:
  - `src/kr_vector_index/chunks.py` builds vector keys as `{entity_type}#{source_id}#{chunk_no}`.
  - `source_id` comes from `content_id`, `entity_id`, or `SK`, but `PK`/city is not part of the key.
  - `chunk_no` is currently `0` for every chunk.
  - `src/kr_vector_index/upsert.py` deduplicates keys only within one SDK put batch, not across Step Functions city batches.
  - `src/kr_vector_index/batch.py` aggregate count sums per-worker `vector_success_count`, which is a write/upsert count, not a current unique-key inventory count.
- Exact overwritten source IDs cannot be reconstructed from the current S3 Vector index alone after replacement. Listing current vectors shows only the surviving value for each key.

This task did not run DynamoDB scans, vector writes, deletes, re-upserts, rebuilds, or index reconciliation.

## Evidence Boundary

Allowed by `docs/specs/TASK10_SUBTASKS.md`:

- read-only S3 Vector list/query operations
- source code inspection
- report writing under `docs/reports/`

Not performed:

- S3 Vector delete/recreate/replacement
- another full vector rebuild
- manual vector re-upsert
- DynamoDB mutation
- S3 object deletion
- enrichment backfill

## Source Count Versus Current Unique Count

Manifest from Task 8:

| Entity | Manifest count | Current unique vector count | Delta |
|---|---:|---:|---:|
| attraction | 7024 | 6973 | 51 |
| festival | 398 | 393 | 5 |
| city/city_metadata | 240 | 240 | 0 |
| total | 7662 | 7606 | 56 |

Interpretation:

- City vectors match exactly.
- The loss is concentrated in `attraction` and `festival`, where external source IDs are more likely to appear under more than one city PK.
- `visitor_statistics` is not part of the discrepancy.

## S3 Vector List Evidence

Read-only current index count:

```json
{
  "vector_count": 7606,
  "visitor_statistics_vectors": 0,
  "metadata_entity_counts": {
    "attraction": 6973,
    "city": 240,
    "festival": 393
  },
  "key_prefix_counts": {
    "attraction": 6973,
    "city": 240,
    "festival": 393
  },
  "chunk_no_counts": {
    "0": 7606
  },
  "bad_key_pattern_count": 0,
  "metadata_key_entity_mismatch_count": 0,
  "sample_keys": [
    "attraction#2765245#0",
    "attraction#2022531#0",
    "attraction#3072039#0",
    "attraction#2728939#0",
    "attraction#127586#0"
  ]
}
```

What this proves:

- Current S3 Vector inventory contains `7606` unique keys.
- `visitor_statistics_vectors=0`, preserving the separate invariant from Task 7-9.
- Every current key follows the expected `{entity_type}#{source_id}#{chunk_no}` pattern.
- Every current key has `chunk_no=0`.
- Metadata entity type and key prefix agree for all current vectors.

What this cannot prove by itself:

- Which overwritten source IDs produced the missing 56 writes.
- Whether duplicate source IDs came from the same external content assigned to multiple city PKs, stale source rows, or an upstream identity merge issue.

The current index only contains surviving unique keys. Replaced vectors are not available through `list-vectors`.

## Query Evidence

Read-only sample query remained valid:

```json
{
  "distanceMetric": "cosine",
  "top_key": "attraction#2765245#0",
  "top_distance": 0.00003063678741455078,
  "top_entity_type": "attraction",
  "top_ddb_pk": "CITY#SEOGWIPO",
  "top_ddb_sk": "ATTRACTION#2765245"
}
```

This confirms the index is queryable and the known sample key still resolves.

## Code Path Analysis

### Key Construction

`src/kr_vector_index/chunks.py` constructs keys this way:

```python
entity_type = _normalize_entity_type(str(item.get("entity_type") or "unknown"))
source_id = str(item.get("content_id") or item.get("entity_id") or _sk_source_id(item) or "unknown")
place_id = f"{entity_type}#{source_id}"
key = f"{place_id}#{chunk_no}"
```

The key does not include:

- DynamoDB `PK`
- city identifier
- raw S3 URI
- source city

Therefore two vectorizable rows with the same entity type and source ID produce the same S3 Vector key even if they are under different city PKs.

### Upsert Counting

`src/kr_vector_index/upsert.py` removes duplicate keys only within one SDK put batch:

```python
seen_keys: set[str] = set()
deduped: list[dict[str, Any]] = []
for record in batch:
    key = record.get("key", "")
    if key not in seen_keys:
        seen_keys.add(key)
        deduped.append(record)
```

The deduplication set is local to one put batch. Step Functions processes city batches independently, so the same key can be successfully put again in a later city batch.

### Aggregate Counting

`src/kr_vector_index/batch.py` computes aggregate success by summing worker summaries:

```python
vector_success_count += int(summary.get("vector_success_count", 0) or 0)
```

That value is an accepted write/upsert count. It is not a distinct-key count after all upserts have settled in the target index.

## Cause Classification

| Candidate cause | Classification | Evidence |
|---|---|---|
| Duplicate keys | Most likely verified mechanism | Key omits city/PK and uses `{entity_type}#{source_id}#0`; current count is lower only for attraction/festival; city count matches exactly |
| S3 Vector upsert replacement | Most likely verified mechanism | PutVectors with the same key produces one current unique vector; aggregate counts accepted writes, not final unique inventory |
| List semantics alone | Unlikely as primary cause | Paginated list completed consistently; key prefix counts match metadata counts; bad key pattern count is `0` |
| Stale replacement | Possible subtype of upsert replacement | A stale row with an existing key would overwrite the earlier vector; exact stale rows are not recoverable from current index alone |
| Failed batches | Rejected | Task 8 aggregate reported `failed_count=0` and `failed_batch_ids=[]` |
| `visitor_statistics` inclusion | Rejected | `visitor_statistics_vectors=0` |
| Metadata/key mismatch | Rejected for current inventory | `metadata_key_entity_mismatch_count=0` |

## Operational Impact

The full vector rebuild did succeed as an execution workflow:

- Step Functions reached `SUCCEEDED`.
- Aggregate failed batch count was `0`.
- Manifest was written.
- Current index is queryable.
- `visitor_statistics` remains excluded.

The remaining limitation is inventory semantics:

- `vector_success_count=7662` should be read as accepted write/upsert count.
- `vector_count=7606` should be read as current unique-key inventory.
- The current index cannot prove a one-to-one mapping from source rows to unique vectors.

## Recommended Follow-Up

If exact overwritten IDs are needed, run a separately approved read-only source-side duplicate-key audit:

1. Recompute candidate vector keys from source DynamoDB rows or the same planner input.
2. Group by `{entity_type}#{source_id}#0`.
3. Report groups with count greater than 1, including PK/SK/city for each duplicate.
4. Decide whether key design should include `PK`/city or whether duplicates should be deduplicated upstream before write.

Do not change key design or rewrite the index without a separate approved Task.
