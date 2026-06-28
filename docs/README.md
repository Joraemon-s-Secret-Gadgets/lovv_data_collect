# Lovv Data Collect Docs

이 폴더는 Lovv 데이터 수집, 전처리, 벡터 인덱싱, 운영 검토 문서의 작업 기준을 모아 둔다.

## 문서 사용 기준

- PRD는 사용자 요구와 범위를 정의한다.
- Spec은 구현 계약, 데이터 모델, 수용 기준, 검증 명령을 정의한다.
- Plan은 구현 순서와 작업 분해를 정의한다.
- Report는 완료 결과, 운영 검토, 조사 결론, 후속 액션을 기록한다.
- Agent 운영 문서는 `docs/agents/` 아래에 유지하고 일반 기능 문서와 섞지 않는다.

## 주요 문서

| 구분 | 문서 | 목적 |
| --- | --- | --- |
| PRD | [data_pipeline_prd.md](data_pipeline_prd.md) | KR 데이터 파이프라인 요구사항 |
| PRD | [s3_vector_index_prd.md](s3_vector_index_prd.md) | S3 Vector 인덱스 요구사항 |
| PRD | [classification_vector_enrichment_prd.md](classification_vector_enrichment_prd.md) | classification dict 기반 class-aware vector 요구사항 |
| Plan | [data_preprocessing_plan.md](data_preprocessing_plan.md) | 데이터 전처리 운영 계획 |
| Plan | [japan_data_acquisition_plan.md](japan_data_acquisition_plan.md) | JP 도시·관광지 데이터 취득 계획 |
| Plan | [s3_vector_index_implementation_plan.md](s3_vector_index_implementation_plan.md) | S3 Vector 인덱스 구현 계획 |

## Specs

| 문서 | 목적 |
| --- | --- |
| [specs/data_pipeline_spec.md](specs/data_pipeline_spec.md) | KR 데이터 파이프라인 구현 계약 |
| [specs/s3_vector_index_spec.md](specs/s3_vector_index_spec.md) | S3 Vector 인덱스 구현 계약 |
| [specs/classification_vector_enrichment_spec.md](specs/classification_vector_enrichment_spec.md) | class-aware vector enrichment 구현 계약 |
| [specs/raw_preprocessing_dynamodb_spec.md](specs/raw_preprocessing_dynamodb_spec.md) | Raw preprocessing 및 DynamoDB 적재 계약 |
| [specs/kr_details_elt_spec.md](specs/kr_details_elt_spec.md) | KR 상세 데이터 ELT 계약 |
| [specs/city_data_acquisition_spec.md](specs/city_data_acquisition_spec.md) | City 데이터 취득 계약 |
| [specs/city_data_acquisition_spec_ko.md](specs/city_data_acquisition_spec_ko.md) | City 데이터 취득 계약 한국어본 |

## Guides

| 문서 | 목적 |
| --- | --- |
| [guides/dynamodb_v2_query_guide.md](guides/dynamodb_v2_query_guide.md) | `TourKoreaDomainDataV2` 조회, PK/SK, GSI, `visitor_statistics` 사용 가이드 |
| [guides/dynamodb_query_guide.md](guides/dynamodb_query_guide.md) | 기존 DynamoDB 조회 패턴 참고 문서 |

## Reports

| 문서 | 목적 |
| --- | --- |
| [reports/korea_data_preprocessing_result_report.md](reports/korea_data_preprocessing_result_report.md) | KR 전처리 결과 보고 |
| [reports/kr_nationwide_pipeline_report_20260628.md](reports/kr_nationwide_pipeline_report_20260628.md) | 2026-06-28 AWS live 조회 기준 전국 전처리·적재 보고 |
| [reports/preprocessing_report.md](reports/preprocessing_report.md) | 2026-06-10 40개 도시 기준 과거 전처리 검증 보고 |
| [reports/query_usage_guide.md](reports/query_usage_guide.md) | 기존 `TourKoreaDomainData` 조회 및 S3 키 패턴 legacy 참고 문서 |
| [reports/s3_vector_index_infra_report.md](reports/s3_vector_index_infra_report.md) | S3 Vector 인프라 작업 보고 |
| [reports/s3_vector_graphrag_usage_report.md](reports/s3_vector_graphrag_usage_report.md) | GraphRAG 검색 사용 보고 |
| [reports/s3_vector_console_test_usage.md](reports/s3_vector_console_test_usage.md) | S3 Vector 콘솔 테스트 사용 기록 |
| [reports/graphrag_lambda_implementation_review.md](reports/graphrag_lambda_implementation_review.md) | GraphRAG Lambda 구현 리뷰 |
| [reports/coderabbit_review_response_plan.md](reports/coderabbit_review_response_plan.md) | CodeRabbitAI 리뷰 대응 계획 |
| [reports/japan_data_source_license_investigation_report.md](reports/japan_data_source_license_investigation_report.md) | JP 데이터 소스·라이선스 조사 결과 |
| [reports/work_progress_report.md](reports/work_progress_report.md) | 작업 진행 보고 |

## Agent 운영 문서

Agent 운영 규칙, 실행 모드, 리뷰 포맷, 보안 체크리스트는 [agents/](agents/) 아래에 둔다. 한국어 보조 문서는 [agents/ko/](agents/ko/)에 유지한다.

## 작성 규칙

- 새 요구사항 문서는 `docs/*_prd.md`에 둔다.
- 구현 계약은 `docs/specs/*_spec.md`에 둔다.
- 조사·검토·완료 보고는 `docs/reports/*.md`에 둔다.
- 대화용 프롬프트는 `docs/prompts/`에 둔다.
- 문서 간 관련성이 있으면 상대 경로 링크를 추가한다.
