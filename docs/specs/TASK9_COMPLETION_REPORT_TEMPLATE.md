# TASK9_COMPLETION_REPORT_TEMPLATE: KR Lambda/SFN Final Evidence Gate

> Source of Truth: `.kiro/specs/kr-lambda-sfn-batch-reset/requirements.md`
> Task Plan: `.kiro/specs/kr-lambda-sfn-batch-reset/tasks.md`
> Active Goal Audit: `docs/reports/kr_lambda_sfn_batch_reset_goal_audit_20260630.md`
> Base branch: `investigate/enrichment-field-loading-20260628`
> Output report path: `docs/reports/kr_lambda_sfn_batch_reset_completion_YYYYMMDD.md`

## Purpose

Task 9의 최종 한국어 완료 보고서가 active goal의 필수 범위를 축소하지 않도록 evidence gate를 고정한다.

최종 보고서는 다음 세 가지를 반드시 직접 증명해야 한다.

1. 계속 누락되던 `visitor_statistics` / 방문자 통계 coverage가 보완 및 재검증되었다.
2. 현재 브랜치 `investigate/enrichment-field-loading-20260628`의 enrichment field loading/backfill 의도가 reset, verification gate, vector metadata 검증, final report에 유지되었다.
3. DynamoDB/S3/S3 Vector protected data-plane 리소스가 Terraform apply, smoke test, full rebuild 과정에서 삭제 또는 재생성 대상이 아니었다.

## Completion Preconditions

최종 보고서는 아래 조건이 충족되기 전에는 "완료"로 작성하지 않는다.

- Terraform apply가 명시 승인 후 저장된 plan artifact로 실행되었다.
- Post-apply live verifier가 loader-owned vector route 제거, delete permission 제거, visitor/enrichment gate 배치를 검증했다.
- Bounded vector planner smoke test가 `visitor_statistics` 제외와 enrichment mode를 기록했다.
- Bounded vector worker smoke test가 timeout 없이 종료되었거나, dry-run/write mode 제한과 실패 사유가 기록되었다.
- Full vector rebuild는 실행 결과를 기록하거나, 미실행이면 사용자 승인/보류 사유를 기록했다.
- `visitor_statistics` count, city coverage, residual city PKs, key-shape checks, vector exclusion evidence가 포함되었다.
- Enrichment field counts, vector metadata enrichment field counts, and full `metadata_enrichment` exclusion evidence가 포함되었다.

## Required Report Sections

### 1. Executive Summary

- 완료 여부: `complete`, `partial`, `blocked`, or `not-run`.
- Terraform apply status.
- Smoke test status.
- Full vector rebuild status.
- Remaining risks and required user decisions.

### 2. Active Goal Scope Lock

반드시 아래 문장을 현재 결과에 맞게 채워 넣는다.

```text
Active goal scope was preserved.
- visitor_statistics coverage: [verified/not verified], live rows: [count], city coverage: [coverage]
- branch intent: investigate/enrichment-field-loading-20260628, enrichment mode: [mode]
- protected data plane: [verified/not verified], destructive protected actions: [none/list]
```

### 3. Visitor Statistics Evidence

Required fields:

| Field | Required value or evidence |
|---|---|
| DataLab raw contract | `raw/KR/datalab/20260629/visitor_statistics_2025.json` |
| local source reference | `data/KR/visitor_statistics_2025.json` |
| DynamoDB table | `TourKoreaDomainDataV2` |
| entity type | `visitor_statistics` |
| live row count | expected `2,820`, or approved deviation |
| city coverage | expected `235 city PKs x 12 months`, or approved deviation |
| residual city PKs | list or link to report section |
| SK shape | `STAT#{YYYYMM}` |
| domain_sort_key shape | `STAT#{YYYYMM}` |
| `gsi_sk` pollution | expected `0` |
| vector exclusion | planner/export evidence that vector count remains `0` for `visitor_statistics` |

Stop condition: if live count drops below 2,820 without an approved explanation, do not mark the goal complete.

### 4. Enrichment Field Loading Evidence

Required fields:

| Field | Required evidence |
|---|---|
| branch name | `investigate/enrichment-field-loading-20260628` |
| attraction rows | latest live count |
| `metadata_enrichment` count | latest live count |
| `indoor_outdoor` count | latest live count |
| `vibe_tags` count | latest live count |
| `experience_tags` count | latest live count |
| `companion_fit` count | latest live count |
| `schema_version` count | latest live count |
| enrichment mode | `enrichment-complete`, `non-enrichment-complete`, or approved equivalent |
| vector metadata derived field counts | sampled or aggregate evidence |
| full `metadata_enrichment` exclusion | explicit sample or verifier evidence |

Stop condition: if live enrichment field counts remain `0`, the report may state routing/smoke rebuild behavior is verified, but must not claim enrichment-complete vector output.

### 5. Protected Data Plane Evidence

Required fields:

| Resource class | Required evidence |
|---|---|
| DynamoDB tables | no delete/recreate in plan and post-apply checks |
| S3 buckets | no delete/recreate in plan and post-apply checks |
| S3 objects | no unapproved delete actions |
| S3 Vector index | no delete/recreate unless separately approved |
| `terraform_data.kr_vector_index` shim | no-op unless separately approved |

Include Terraform plan guard CLI output:

```powershell
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
```

### 6. Apply And Live Wiring Evidence

Required evidence:

- Terraform apply command and result.
- Lambda config evidence for `kr-pipeline-loader` and `kr-pipeline-vector`.
- IAM evidence that `dynamodb:DeleteItem` and `s3:DeleteObject` are absent from the Lambda execution policy.
- Step Functions evidence that `VisitorStatsCoverageGate`, `EnrichmentFieldLoadingGate`, `VectorPlanStage`, `VectorBatchStage`, and `VectorAggregateStage` exist.
- Evidence that Step Functions no longer invokes `kr-pipeline-loader` with `command="vector-build"`.

### 7. Smoke And Rebuild Evidence

Required evidence:

- Planner smoke input, item limit, batch size, response summary, and `visitor_statistics` exclusion.
- Worker smoke mode: dry-run or approved limited write.
- Worker duration and timeout result.
- Worker item count, chunk count, vector success count, failure count, and failed batch details.
- Whether Task 7 followed `docs/specs/TASK7_APPLY_SMOKE_RUNBOOK.md`.
- Full vector rebuild execution id and manifest path, or approved reason why it was not run.
- Final vector counts and sample query evidence if full rebuild ran.

### 8. Review Result

Required checks:

- Spec alignment checklist for Requirements 3, 4, 5, 7, 8, and 9.
- Security review result for IAM and protected data plane.
- Test/verification commands with pass/fail status.
- Known limitations and follow-up tasks.
- User confirmation items.

## Verification Commands

Run or explicitly mark as not applicable with reason:

```powershell
git diff --check
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform show -json "../../.cache/terraform/kr-lambda-sfn-batch-reset.tfplan" | uv run python -m kr_vector_index.terraform_plan_guard_cli
$env:UV_CACHE_DIR='.cache\uv'
uv run python -m kr_vector_index.live_verification_cli
uv run python -m pytest src\kr_vector_index\tests --basetemp .cache\pytest-vector-index-final -p no:cacheprovider
```

## Final Report Stop Conditions

Do not mark the active goal complete if any of these remain true:

- Terraform apply was not approved or not executed.
- Post-apply live verifier still reports old loader vector routing.
- Lambda IAM still includes runtime delete permissions.
- `visitor_statistics` live evidence is missing or below baseline without approved explanation.
- `visitor_statistics` vector exclusion is not proven.
- Enrichment field loading/backfill status is omitted.
- The report claims enrichment-complete while live enrichment counts remain zero.
- Full vector rebuild status is omitted.
- Protected DynamoDB/S3/S3 Vector plan/apply evidence is omitted.
