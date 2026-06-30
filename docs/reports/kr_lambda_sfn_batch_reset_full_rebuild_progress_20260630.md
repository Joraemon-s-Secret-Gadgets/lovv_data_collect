# KR Lambda/SFN Batch Reset Full Rebuild Progress - 2026-06-30

## Snapshot

- 작성 시각: 2026-06-30 18:16:17 +09:00
- Responsible agent: Main Codex as Implementation/Review coordinator
- Branch: `investigate/enrichment-field-loading-20260628`
- Task: Task 8 full vector rebuild after smoke-test approval
- Execution mode: Sequential Mode

## Approval And Target

사용자는 Task 8 실행 전에 다음 범위를 승인했다.

- full Step Functions vector rebuild execution
- non-dry-run S3 Vector writes
- aggregate execution and manifest write
- target vector bucket/index: `lovv-vector-dev` / `kr-tour-domain-v2`
- Step Functions Map concurrency: `MaxConcurrency=5`
- retry policy: bounded retry/redrive only
- no S3 Vector index deletion, recreation, or replacement

Approval artifact:

- `docs/reports/kr_lambda_sfn_batch_reset_full_rebuild_approval_20260630.md`

## Pre-Rebuild Live Gate

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
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

Interpretation:

- `visitor_statistics` live row count stayed at the approved baseline `2820`.
- Coverage gate stayed `true`.
- Enrichment remains `non-enrichment-complete`; Task 8 must not claim enrichment-complete vector output.

## Terraform Changes Applied During Task 8

### Vector-Only Step Functions Entry

File:

- `infrastructure/terraform/step_functions.tf`

Change:

- State machine `StartAt` now enters `CheckVectorOnly`.
- `run_vector_only=true` routes directly to `VisitorStatsCoverageGate`.
- This prevents Task 8 vector rebuild from rerunning transform/image/load stages.

Apply result:

- Plan: `task8-vector-only.tfplan`
- Apply result: `0 added, 1 changed, 0 destroyed`
- Changed resource: `aws_sfn_state_machine.kr_data_pipeline`

### Image Lambda Package Fix

File:

- `infrastructure/terraform/lambda_image_processor.tf`

Change:

- Archive source changed from `../../src/kr_image_processor` to `../../src`.
- Excludes added for unrelated packages:
  - `kr_details_pipeline/**`
  - `kr_unified_pipeline/**`
  - `kr_vector_index/**`

Reason:

- Full rebuild initially reached final `GenerateReport` and failed with `Runtime.ImportModuleError: No module named 'kr_image_processor'`.
- Packaging fix made the package layout match handler imports.

Apply result:

- Plan: `task8-image-package-fix.tfplan`
- Apply result: `0 added, 1 changed, 0 destroyed`
- Changed resource: `aws_lambda_function.kr_pipeline_image`

## Step Functions Execution

Execution ARN:

```text
arn:aws:states:us-east-1:925273580929:execution:kr-data-pipeline-dev:task8-vector-rebuild-20260630-174818
```

Input:

```json
{
  "run_vector_only": true,
  "bucket": "lovv-data-pipeline-dev-925273580929",
  "ingest_date": "20260630",
  "task": "TASK8_FULL_VECTOR_REBUILD",
  "approved_vector_bucket": "lovv-vector-dev",
  "approved_vector_index": "kr-tour-domain-v2"
}
```

Final describe summary:

```json
{
  "status": "SUCCEEDED",
  "startDate": "2026-06-30T17:48:20.312+09:00",
  "stopDate": "2026-06-30T18:08:29.678+09:00",
  "redriveCount": 1,
  "vectorStatus": "succeeded",
  "batchCount": 240,
  "itemCount": 7662,
  "chunkCount": 7662,
  "vectorSuccessCount": 7662,
  "failedCount": 0,
  "failedBatchCount": 0,
  "failedBatchIds": [],
  "manifestS3Uri": "s3://lovv-data-pipeline-dev-925273580929/processed/KR/vector/manifests/latest.json",
  "visitorStatisticsRows": 2820,
  "visitorStatisticsCoverageOk": true,
  "enrichmentMode": "non-enrichment-complete",
  "metadataEnrichment": 0,
  "indoorOutdoor": 0,
  "vibeTags": 0,
  "experienceTags": 0,
  "companionFit": 0,
  "schemaVersion": 0
}
```

Failure and recovery:

- Initial execution failed only at final `GenerateReport`.
- Failure reason: image Lambda import packaging error for `kr_image_processor`.
- Fix: adjusted `kr-pipeline-image` package archive source and excludes.
- Recovery: `aws stepfunctions redrive-execution ...`
- Final result: `SUCCEEDED`.

## Aggregate Manifest

Manifest path:

```text
s3://lovv-data-pipeline-dev-925273580929/processed/KR/vector/manifests/latest.json
```

Manifest body:

```json
{
  "index_name": "kr-tour-domain-v2",
  "index_text_mode": "rich",
  "created_at": "2026-06-30T09:00:22.725925+00:00",
  "entity_counts": {
    "city_metadata": 240,
    "attraction": 7024,
    "festival": 398
  },
  "chunk_count": 7662,
  "vector_success_count": 7662,
  "failed_count": 0,
  "status": "succeeded",
  "batch_count": 240,
  "item_count": 7662,
  "failed_batch_ids": []
}
```

## S3 Vector Index Verification

Target:

- Bucket: `lovv-vector-dev`
- Index: `kr-tour-domain-v2`

Index configuration:

```json
{
  "dataType": "float32",
  "dimension": 1024,
  "distanceMetric": "cosine",
  "encryption": "AES256"
}
```

Current exact paginated list count:

```json
{
  "vector_count": 7606,
  "visitor_statistics_vectors": 0,
  "metadata_counts": {
    "festival": 393,
    "attraction": 6973,
    "city": 240
  }
}
```

Important discrepancy:

- Aggregate/manifest reports `vector_success_count=7662`.
- Current S3 Vector unique list count is `7606`.
- Delta: `56` fewer current unique vectors than aggregate successful writes.
- Breakdown versus manifest entity counts:
  - attraction: manifest `7024`, current `6973`, delta `51`
  - festival: manifest `398`, current `393`, delta `5`
  - city: manifest `240`, current `240`, delta `0`
- Likely explanation candidates: key upsert collisions, replacement of stale keys, duplicate generated keys, or list-count semantics.
- This is not hidden as success-only evidence; Task 9 must explain it before final completion report closes the goal.

Visitor statistics vector exclusion:

- `visitor_statistics_vectors=0`
- Planner/manifest entity counts include only `city_metadata`, `attraction`, and `festival`.

## Sample Query Evidence

Command:

```powershell
aws s3vectors query-vectors --region us-east-1 --vector-bucket-name lovv-vector-dev --index-name kr-tour-domain-v2 --query-vector file://.cache/smoke/query-vector.json --top-k 1 --return-metadata --return-distance --output json
```

Result summary:

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

## Enrichment Evidence

Live Step Functions output and verifier both show:

```json
{
  "enrichmentMode": "non-enrichment-complete",
  "metadataEnrichment": 0,
  "indoorOutdoor": 0,
  "vibeTags": 0,
  "experienceTags": 0,
  "companionFit": 0,
  "schemaVersion": 0
}
```

Interpretation:

- Task 8 verifies vector rebuild behavior in the current non-enrichment-complete state.
- Task 8 does not claim enrichment-complete vector metadata.
- Because succeeded enrichment counts are zero, vector metadata enrichment derived fields cannot be claimed as complete.

## Protected Data-Plane Evidence

Task 8 did not run any protected delete/recreate action.

| Resource class | Evidence |
|---|---|
| DynamoDB tables | No Task 8 delete/recreate command. Task 7 protected plan guard had no protected data-plane destroy. |
| S3 buckets | No Task 8 bucket delete/recreate command. |
| S3 objects | Aggregate wrote manifest; no unapproved delete action. |
| S3 Vector index | `get-index` verified existing `lovv-vector-dev` / `kr-tour-domain-v2`; no delete/recreate/replacement. |
| Terraform scope | Task 8 applies changed only Step Functions state machine and image Lambda package. |

## Local Verification

Commands:

```powershell
terraform -chdir=infrastructure/terraform validate
git diff --check
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
uv run python -m pytest src\kr_vector_index\tests src\kr_image_processor\tests\test_handler.py src\kr_image_processor\tests\test_report.py --basetemp .cache\pytest-task8 -p no:cacheprovider
```

Results:

- Terraform validate: passed
- `git diff --check`: passed
- Live verifier: passed
- Focused pytest: `69 passed in 0.56s`

## Remaining Risks For Task 9

- Explain and classify the `7662` aggregate success count versus `7606` current unique vector count.
- Preserve the `non-enrichment-complete` wording; do not claim enrichment-complete output.
- Carry forward visitor statistics evidence, including residual legacy city PKs and key-shape checks from the verifier/baseline.
- Review the image Lambda packaging fix as part of Task 9 because it was discovered during final report generation.
- Stop before any follow-up cleanup unless the user explicitly approves it.
