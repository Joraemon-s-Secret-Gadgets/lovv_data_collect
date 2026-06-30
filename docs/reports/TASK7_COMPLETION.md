# TASK7 Completion Report: KR Lambda/SFN Apply And Bounded Smoke

## Completion Timestamp

- 2026-06-30 16:55:37 +09:00

## Responsible Agent

- Main Codex as Implementation/Review coordinator

## Scope

Task 7은 승인된 Terraform 실행계층 reset을 실제 AWS에 반영하고, post-apply live verification 및 bounded vector smoke test로 Lambda/SFN wiring을 검증했다.

이번 Task에서 실행하지 않은 작업:

- aggregate command
- full Step Functions vector rebuild
- non-dry-run worker write
- S3 Vector index deletion, recreation, or replacement

현재 브랜치:

- `investigate/enrichment-field-loading-20260628`

## Spec Alignment Checklist

| Requirement | Status | Evidence |
|---|---|---|
| 승인된 Terraform plan으로만 apply | Satisfied | Pre-apply plan remained `0 to add, 5 to change, 0 to destroy` |
| 보호 data-plane 삭제/재생성 금지 | Satisfied | Plan guard passed; protected resources all `no-op` |
| Lambda/SFN execution-plane reset 반영 | Satisfied | Apply result `0 added, 5 changed, 0 destroyed` |
| smoke 중 발견된 IAM 누락 보완 | Satisfied | `TourKoreaDomainDataV2` 대상 `dynamodb:Scan` 권한 추가 후 apply result `0 added, 1 changed, 0 destroyed` |
| post-apply live verifier 통과 | Satisfied | `python -m kr_vector_index.live_verification_cli` exit code `0` |
| `visitor_statistics` coverage 보존 | Satisfied | `visitor_statistics_rows=2820`, `visitor_statistics_coverage_ok=true` |
| enrichment branch intent 보존 | Satisfied | `enrichment_mode=non-enrichment-complete`; live enrichment-derived field counts remain non-complete/zero baseline |
| vector planner smoke에서 `visitor_statistics` 제외 | Satisfied | planner `entity_counts={city_metadata: 5}` and no `visitor_statistics` |
| bounded worker smoke timeout 없음 | Satisfied | one dry-run batch completed with `failed_count=0` |
| full rebuild 전 중단 | Satisfied | aggregate/full rebuild not run during Task 7 |

## Changed Files And Implementation Summary

Task 7에서 실제 AWS 상태가 변경된 범위:

- Terraform apply 1차: IAM policy, Lambda 3개, Step Functions
- IAM 보완 apply: `dynamodb:Scan` 권한 추가 for `TourKoreaDomainDataV2`

Task 7 handoff/report artifact:

- `docs/reports/TASK7_COMPLETION.md`
- `docs/specs/TASK8_SUBTASKS.md`
- `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`

Task 7 smoke는 `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`의 dry-run boundary를 따랐다. Worker는 `dry_run=true`로 실행했으므로 Bedrock embedding write 및 S3 Vector write는 기대하지 않았고, `vector_success_count=0`은 정상 결과다.

## Verification Results

### Subtask 1: Pre-Apply Verification

Commands and gates:

```powershell
terraform -chdir=infrastructure/terraform plan -out="../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Results:

- Terraform plan: `0 to add, 5 to change, 0 to destroy`
- Plan guard: passed
- Protected resources: all `no-op`
- Live verifier: exit code `1`, expected because old live drift still existed before apply
- Expected old drift: loader vector routing/delete permission/desired SFN state drift

### Subtask 2: Terraform Apply

Command:

```powershell
terraform -chdir=infrastructure/terraform apply "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan"
```

Result:

- `0 added, 5 changed, 0 destroyed`
- Changed resource classes:
  - IAM policy
  - Lambda functions: 3
  - Step Functions state machine

Additional IAM fix discovered during smoke:

- Added `dynamodb:Scan` for `TourKoreaDomainDataV2`
- Additional apply result: `0 added, 1 changed, 0 destroyed`

### Subtask 3: Post-Apply Live Verification

Command:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
```

Result:

- Exit code: `0`
- Old drift resolved: yes
- `visitor_statistics_rows`: `2820`
- `visitor_statistics_coverage_ok`: `true`
- `enrichment_mode`: `non-enrichment-complete`

Interpretation:

- Live AWS no longer matches the pre-apply old drift state.
- `visitor_statistics` coverage stayed above the stop threshold.
- Enrichment field loading/backfill remains non-complete; Task 7 does not claim enrichment-complete vector output.

### Subtask 4: Vector Planner Smoke

Preflight result:

- Status: passed
- Table: `TourKoreaDomainDataV2`
- Entity index: `EntityTypeDomainIndex`
- Visitor statistics coverage: preserved
- Enrichment mode: `non-enrichment-complete`

Planner input summary:

- `command`: `plan`
- `table_name`: `TourKoreaDomainDataV2`
- `entity_index_name`: `EntityTypeDomainIndex`
- `vector_bucket`: `lovv-vector-dev`
- `index_name`: `kr-tour-domain-v2`
- `max_items`: `5`
- `batch_size`: `1`
- `enrichment_mode`: `non-enrichment-complete`
- `visitor_statistics_coverage_ok`: `true`

Planner result:

- `batch_count`: `5`
- `entity_counts`: `{city_metadata: 5}`
- `visitor_statistics`: not included

### Subtask 5: Worker Dry-Run Smoke

Worker input summary:

- `command`: `worker`
- `dry_run`: `true`
- `batch_id`: `kr-vector-000001`

Worker result:

- `batch_id`: `kr-vector-000001`
- `item_count`: `1`
- `chunk_count`: `1`
- `vector_success_count`: `0`
- `failed_count`: `0`
- Lambda timeout: none observed

Interpretation:

- `vector_success_count=0` is expected because the worker was explicitly executed in dry-run mode.
- No S3 Vector write was approved or attempted in Task 7.

## Protected Data-Plane Evidence

| Resource class | Task 7 evidence |
|---|---|
| DynamoDB tables | Plan guard passed; protected tables remained `no-op`; apply summary had no destroy |
| S3 buckets | Plan guard passed; protected buckets remained `no-op`; apply summary had no destroy |
| S3 objects | No unapproved delete action was run |
| S3 Vector index | No deletion, recreation, replacement, or full rebuild was run |
| `terraform_data.kr_vector_index` shim | Protected plan guard kept it no-op |

## Task 7 Stop Boundary

Task 7 stopped before all actions that require separate approval:

- full Step Functions vector execution
- non-dry-run worker writes
- aggregate manifest write
- full vector rebuild
- S3 Vector index deletion or recreation

## Remaining Risks And Decisions

- Task 8 still requires explicit user approval before any real vector write.
- Task 8 also requires explicit approval before `aggregate`, because it may write a manifest to S3 when `MANIFEST_BUCKET` is configured.
- Full rebuild output, final vector counts, sample query evidence, and aggregate manifest evidence are not available yet because Task 8 has not run.
- Enrichment-derived live fields remain in `non-enrichment-complete` state, so final reporting must not claim enrichment-complete vector output unless later live evidence changes.

## Next-Agent Instruction Sheet

- `docs/specs/TASK8_SUBTASKS.md`

Start Task 8 only after the user explicitly approves full vector rebuild execution, real write mode, and aggregate/manifest behavior.
