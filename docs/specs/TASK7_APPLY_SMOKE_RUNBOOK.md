# TASK7_APPLY_SMOKE_RUNBOOK: KR Lambda/SFN Apply And Bounded Smoke

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Task Sheet: `docs/specs/TASK7_SUBTASKS.md`
> Apply Approval Package: `docs/reports/kr_lambda_sfn_batch_reset_apply_approval_20260630.md`
> Active Goal Audit: `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`
> Next-Session Handoff: `docs/reports/kr_lambda_sfn_batch_reset_next_session_handoff_20260630.md`
> Base branch: `investigate/enrichment-field-loading-20260628`

## Purpose

이 runbook은 Task 7 실행자가 Terraform apply 승인 이후 bounded smoke test를 같은 순서와 같은 write boundary로 실행하도록 고정한다.

Do not run this runbook before explicit Terraform apply approval.

## Safety Boundaries

- Run Terraform apply only with the reviewed saved plan artifact.
- Do not delete Lambda, Step Functions, DynamoDB, S3 buckets, S3 objects, or S3 Vector indexes manually.
- Do not run full Step Functions vector rebuild during Task 7.
- Do not run live worker write mode unless the user explicitly approves limited S3 Vector writes.
- For Task 7 smoke, invoke worker with `dry_run=true`.
- Do not invoke `aggregate` during dry-run-only smoke. `aggregate` may write a manifest to S3 when `MANIFEST_BUCKET` is configured.
- Stop if `visitor_statistics` coverage drops below 2,820 rows without approved explanation.
- Stop if enrichment mode is reported as complete while live enrichment counts remain zero.

## Pre-Apply Refresh

These commands are non-destructive and may be rerun before approval:

```powershell
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Expected pre-apply interpretation:

- Terraform plan remains `0 to add, 5 to change, 0 to destroy`.
- Plan guard passes and protected DynamoDB/S3/S3 Vector resources remain `no-op`.
- Live verifier exits `1` only because old loader vector routing, old delete permissions, and missing desired Step Functions states are still live.
- Live verifier observations must still include:
  - `visitor_statistics_rows=2820`
  - `visitor_statistics_coverage_ok=true`
  - `enrichment_mode=non-enrichment-complete`, unless a newer approved enrichment mode exists.

## Apply

Run only after explicit user approval:

```powershell
terraform -chdir=infrastructure/terraform apply "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

Record the apply result in the Task 7 completion report.

## Post-Apply Live Wiring Gate

Immediately after apply:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Expected post-apply result:

- exit code `0`
- no loader vector environment variables
- no Lambda runtime `dynamodb:DeleteItem`
- no Lambda runtime `s3:DeleteObject`
- Step Functions includes `VisitorStatsCoverageGate`, `EnrichmentFieldLoadingGate`, `VectorPlanStage`, `VectorBatchStage`, and `VectorAggregateStage`
- Step Functions no longer invokes `kr-pipeline-loader` with `command="vector-build"`
- observations still preserve `visitor_statistics` coverage and enrichment mode.

Any post-apply verifier failure is a Task 7 blocker.

## Bounded Planner Smoke

Create a smoke output directory:

```powershell
New-Item -ItemType Directory -Force -Path ".cache\smoke" | Out-Null
```

Invoke preflight on the live vector Lambda:

```powershell
$payload = @{
  command = "preflight"
  table_name = "TourKoreaDomainDataV2"
  entity_index_name = "EntityTypeDomainIndex"
} | ConvertTo-Json -Compress

aws lambda invoke `
  --function-name kr-pipeline-vector `
  --region us-east-1 `
  --cli-binary-format raw-in-base64-out `
  --payload $payload `
  ".cache\smoke\preflight.json"

$preflight = Get-Content ".cache\smoke\preflight.json" -Raw | ConvertFrom-Json
$preflight.summary.visitor_statistics
$preflight.summary.enrichment
```

Required checks:

- `summary.visitor_statistics.row_count` is `2820`.
- `summary.visitor_statistics.coverage_ok` is `true`.
- `summary.enrichment.mode` is accurate.

Invoke planner with a small bound:

```powershell
$payload = @{
  command = "plan"
  table_name = "TourKoreaDomainDataV2"
  entity_index_name = "EntityTypeDomainIndex"
  vector_bucket = "lovv-vector-dev"
  index_name = "kr-tour-domain-v2"
  max_items = 5
  batch_size = 1
  enrichment_mode = $preflight.summary.enrichment.mode
  visitor_statistics_coverage_ok = $preflight.summary.visitor_statistics.coverage_ok
} | ConvertTo-Json -Compress

aws lambda invoke `
  --function-name kr-pipeline-vector `
  --region us-east-1 `
  --cli-binary-format raw-in-base64-out `
  --payload $payload `
  ".cache\smoke\plan.json"

$plan = Get-Content ".cache\smoke\plan.json" -Raw | ConvertFrom-Json
$plan.summary
$plan.batches | Select-Object -First 3
```

Required checks:

- `summary.batch_count` is greater than `0`.
- `summary.visitor_statistics_coverage_ok` is `true`.
- `summary.enrichment_mode` matches preflight.
- `summary.entity_counts` does not include `visitor_statistics`.
- `batches[0]` exists and targets `lovv-vector-dev` / `kr-tour-domain-v2`.

## Bounded Worker Dry-Run Smoke

Invoke exactly one planner-derived batch in dry-run mode:

```powershell
$firstBatch = $plan.batches[0]
$payload = @{
  command = "worker"
  dry_run = $true
  batch = $firstBatch
} | ConvertTo-Json -Depth 10 -Compress

aws lambda invoke `
  --function-name kr-pipeline-vector `
  --region us-east-1 `
  --cli-binary-format raw-in-base64-out `
  --payload $payload `
  ".cache\smoke\worker-dry-run.json"

$worker = Get-Content ".cache\smoke\worker-dry-run.json" -Raw | ConvertFrom-Json
$worker.summary
```

Required checks:

- `summary.command` is `worker`.
- `summary.batch_id` matches the planner batch.
- `summary.item_count` is bounded by the planner batch `max_items`.
- `summary.chunk_count` is recorded.
- `summary.vector_success_count` is `0` in dry-run mode.
- No Bedrock embedding write or S3 Vector write is expected in dry-run mode.

## Task 7 Report Evidence

Task 7 completion report must include:

- Terraform apply command and result.
- Live verifier post-apply output.
- Preflight smoke summary.
- Planner smoke payload summary and batch count.
- Worker dry-run payload summary, item count, chunk count, vector success count, and duration if measured.
- Statement that aggregate/full rebuild was not run during Task 7.
- Current `visitor_statistics` coverage evidence.
- Current branch `investigate/enrichment-field-loading-20260628`.
- Current enrichment mode and field count evidence.
- Protected data-plane plan guard result.

## Stop Before Task 8

After Task 7 smoke, stop and request explicit approval before:

- full Step Functions vector execution,
- non-dry-run worker writes,
- aggregate manifest write,
- full vector rebuild,
- S3 Vector index deletion or recreation.
