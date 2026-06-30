# KR Lambda/SFN Batch Reset Baseline - 2026-06-30

## Summary

이 문서는 `kr-lambda-sfn-batch-reset` 실행 전 baseline이다. 목적은 Lambda/SFN 실행 계층의 live drift를 고정하고, Terraform apply 전 확인해야 할 보호 조건을 명확히 남기는 것이다.

이번 baseline은 read-only 조회만 수행했다. Terraform apply, Lambda 삭제, Step Functions 업데이트, DynamoDB/S3 쓰기, S3 Vector rebuild는 수행하지 않았다.

## Current Branch and Gate Context

- Current branch intent: `investigate/enrichment-field-loading-20260628`
- Kiro spec: `.kiro/specs/kr-lambda-sfn-batch-reset/`
- Gate report: `docs/reports/kr_lambda_sfn_batch_reset_gate_report_20260630.md`

The reset work must preserve two non-negotiable gates:

1. `visitor_statistics` coverage gate
2. enrichment field loading/backfill gate

## Live Lambda Baseline

All live Lambda configuration was read from `us-east-1`.

| Function | Handler | Timeout | Memory | Layer |
|---|---|---:|---:|---|
| `kr-pipeline-transform` | `kr_details_pipeline.handlers.domain_loader_handler.handler` | 900 | 1024 | none |
| `kr-pipeline-image` | `kr_image_processor.handlers.image_handler.handler` | 900 | 512 | `lovv-requests-layer-dev:1` |
| `kr-pipeline-loader` | `kr_unified_pipeline.handlers.pipeline_handler.handler` | 900 | 512 | none |
| `kr-pipeline-vector` | `kr_vector_index.handlers.vector_index_handler.handler` | 900 | 1024 | none |

Live function role:

- `arn:aws:iam::925273580929:role/lovv-data-pipeline-lambda-dev`

Important live state:

- `kr-pipeline-loader` description still includes both S3-to-DynamoDB load and vector index rebuild.
- Only `kr-pipeline-image` has a Lambda Layer.
- Lambda Layer state confirms that layers are not currently a general execution-plane pattern across transform/loader/vector.

## Live Step Functions Baseline

State machine:

- Name: `kr-data-pipeline-dev`
- ARN: `arn:aws:states:us-east-1:925273580929:stateMachine:kr-data-pipeline-dev`
- Status: `ACTIVE`
- Role: `arn:aws:iam::925273580929:role/kr-data-pipeline-sfn-dev`

Live stage routing:

| State | Live Resource | Important Parameters |
|---|---|---|
| `TransformStage` | `kr-pipeline-transform` | Map, `MaxConcurrency=10` |
| `ImageStage` | `kr-pipeline-image` | Map, `MaxConcurrency=10` |
| `AggregateReviewManifest` | `kr-pipeline-image` | `command=aggregate_review` |
| `LoadStage` | `kr-pipeline-loader` | `command=load`, `table_name=TourKoreaDomainDataV2` |
| `VectorStage` | `kr-pipeline-loader` | `command=vector-build`, `rebuild_mode=full`, `index_name=kr-tour-domain-v2` |
| `GenerateReport` | `kr-pipeline-image` | `command=generate_report` |

Critical drift:

- Live `VectorStage` still invokes `kr-pipeline-loader`.
- Live `VectorStage` still uses `command=vector-build`.
- Live `VectorStage` still represents full rebuild as a single Lambda task.
- Live state machine has no Step Functions Map/batch worker for vector rebuild.
- Live state machine has no explicit `VisitorStatsCoverageGate` or `EnrichmentFieldLoadingGate`.

## Local Terraform Desired State

Local Terraform currently differs from live AWS:

| Area | Local Terraform |
|---|---|
| `VectorStage` resource | `aws_lambda_function.kr_pipeline_vector.arn` |
| `VectorStage` command | `build` |
| Vector target | `var.kr_vector_index_name` |
| Vector source table | `var.domain_dynamodb_table_name_v2` |
| Vector entity index | `EntityTypeDomainIndex` |

This means local Terraform has partially moved vector work away from loader, but it is not yet the final requested structure.

Remaining local Terraform gaps:

- No vector planner/worker/aggregator split yet.
- No Step Functions Map for vector batches yet.
- No explicit visitor statistics gate in the state machine yet.
- No explicit enrichment field loading gate in the state machine yet.

## IAM Baseline

### Step Functions Role

Role:

- `kr-data-pipeline-sfn-dev`

Inline policies:

- `kr-data-pipeline-sfn-policy-dev`

Attached managed policies:

- none

Important permissions:

- Allows `lambda:InvokeFunction` for:
  - `kr-pipeline-transform`
  - `kr-pipeline-image`
  - `kr-pipeline-loader`
  - `kr-pipeline-vector`
- Allows CloudWatch Logs delivery/write actions.

### Lambda Role

Role:

- `lovv-data-pipeline-lambda-dev`

Inline policies:

- `image-bucket-access`
- `lovv-data-pipeline-lambda-policy-dev`

Attached managed policies:

- none

Important permissions and risks:

- DynamoDB permissions include `PutItem`, `UpdateItem`, `GetItem`, `DeleteItem`, and `Query`.
- S3 permissions include `ListBucket`, `GetObject`, `PutObject`, and `DeleteObject`.
- Bedrock permissions include Titan embedding and Claude model invocation.
- S3 Vectors permissions include `PutVectors` for `lovv-vector-dev/kr-tour-domain-v2`.

Because the Lambda role includes delete-capable permissions, Terraform plan review and runtime payload review must explicitly prove that protected DynamoDB/S3 data-plane resources are not deleted.

## Visitor Statistics Baseline

Live read-only verification confirmed:

| Check | Result |
|---|---:|
| `visitor_statistics` rows | 2,820 |
| distinct city PKs | 235 |
| rows per city PK | 12 for all 235 PKs |
| rows with `gsi_sk` | 0 |
| rows with non-`STAT#` SK | 0 |
| rows missing `domain_sort_key` | 0 |
| rows where `domain_sort_key != SK` | 0 |

This confirms the current visitor statistics gate is satisfied for the documented 235-city coverage baseline.

Residual unresolved city PKs:

- `CITY#BUKJEJU`
- `CITY#CHEONGWON-GUN`
- `CITY#JINHAE`
- `CITY#MASAN`
- `CITY#NAMJEJU`

These are not vector issues and must not be remediated through S3 Vector rebuild.

## Enrichment Loading Baseline

Local verification passed for:

- enrichment persistence adapter behavior
- enrichment backfill runner behavior
- enrichment result handling
- vector metadata allowlist behavior

Live read-only DynamoDB counts:

| Check | Result |
|---|---:|
| attraction rows | 7,024 |
| rows with `metadata_enrichment` | 0 |
| rows with `indoor_outdoor` | 0 |
| rows with `vibe_tags` | 0 |
| rows with `experience_tags` | 0 |
| rows with `companion_fit` | 0 |
| rows with `schema_version` | 0 |

The reset can verify wiring and timeout behavior, but it must not claim enrichment-complete vector rebuild until enrichment backfill writes non-zero successful rows and the vector metadata sample confirms those fields.

## Verification Completed

| Command | Result |
|---|---|
| visitor statistics focused pytest | 20 passed |
| enrichment/vector metadata focused pytest | 62 passed |
| live visitor statistics read-only check | 2,820 rows, 235 city PKs |
| live enrichment field read-only check | 7,024 attractions, 0 enrichment rows |
| `git diff --check` for Kiro spec/report scope | passed |
| trailing whitespace search for Kiro spec/report scope | no matches |

## Reset Readiness

Ready to proceed to Terraform design work:

- live drift is confirmed
- visitor statistics coverage gate is verified
- enrichment field loading gate is represented in Kiro spec and local tests
- enrichment live count gap is explicitly verified as 0 rows and must be backfilled before enrichment-complete claims
- protected data-plane gate is documented

Not ready for Terraform apply:

- final vector planner/worker/aggregator split is not implemented
- Step Functions Map-based vector rebuild is not implemented
- Terraform plan has not been generated or reviewed
- enrichment backfill has not produced non-zero live rows
- user approval for apply has not been requested or granted

## Required Next Steps

1. Implement Terraform/runtime changes for vector planner, worker, aggregator, and `VectorBatchStage` Map.
2. Add or preserve explicit `VisitorStatsCoverageGate` and `EnrichmentFieldLoadingGate` before vector rebuild.
3. Capture live enrichment field counts before claiming enrichment-complete rebuild.
4. Run `terraform validate`.
5. Generate `terraform plan`.
6. Stop before `terraform apply` and request explicit approval.
