# KR 상세 데이터 전처리 완료 보고서

## 1. 보고서 개요

- 작성 기준일: 2026-06-10
- 대상 저장소: `02_lovv_data_collect`
- 대상 범위: KR 상세 Raw 데이터 전처리 및 DynamoDB 적재
- 기준 입력: `s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260609/*.json`
- 기준 산출물: `TourKoreaDomainData`, `processed/KR/domain`
- 관련 Spec:
  - `docs/specs/kr_details_elt_spec.md`
  - `docs/specs/raw_preprocessing_dynamodb_spec.md`
  - `docs/data_preprocessing_plan.md`

본 보고서는 현재 완료된 작업을 기준으로, 한국 상세 Raw JSON을 서비스 적재 가능한 도메인별 데이터로 분리·정규화하고 DynamoDB에 적재한 결과와 남은 리스크를 정리한다.

## 2. 완료 범위 요약

현재 완료된 전처리 작업은 S3에 적재된 강원도/경상북도 상세 Raw JSON 40개 도시 전체를 기준으로 검증되었다.

| 구분 | 완료 내용 | 상태 |
| --- | --- | --- |
| 입력 Raw 기준 | `raw/KR/details/20260609/*.json` 40개 도시 파일을 전처리 기준 입력으로 사용 | 완료 |
| 도메인 분류 | 음식점, 관광지, 축제, 도시 메타데이터, 방문 통계로 분리 | 완료 |
| 도메인별 컬럼 제한 | 각 entity type별 허용 컬럼만 projection | 완료 |
| 품질 판정 | `passed`, `review`, `failed` 기준으로 산출물 분리 | 완료 |
| DynamoDB 적재 | `TourKoreaDomainData` 전체 비움 후 40개 Raw JSON 재적재 | 완료 |
| Lambda 핸들러 | S3 Raw 객체를 읽어 전처리 후 DynamoDB write 수행하는 핸들러 구현 | 완료 |
| 테스트 | 기존 transform/load 단위 테스트 존재 | 부분 완료 |
| 운영 문서 | 전체 재적재 결과와 `TourKoreaDomainData` 조회 기준 반영 | 완료 |

## 3. 구현된 전처리 흐름

현재 구현된 전처리 흐름은 다음 순서로 동작한다.

```text
KR Raw city detail JSON
↓
city metadata 생성
↓
raw content 순회
↓
restaurant / attraction / festival / excluded / failed 분류
↓
도메인별 허용 컬럼 projection
↓
quality_status 및 review_queues 산정
↓
normalized / load / quality / review / failed 산출물 작성
↓
DynamoDB 적재 후보 또는 Lambda 기반 실제 write
```

핵심 구현 파일은 다음과 같다.

| 파일 | 역할 |
| --- | --- |
| `src/kr_details_pipeline/domain_preprocess.py` | 도메인 분류, 컬럼 projection, 품질 요약, 로컬 산출물 생성 |
| `src/kr_details_pipeline/load.py` | DynamoDB item 직렬화 및 write helper |
| `src/kr_details_pipeline/handlers/domain_loader_handler.py` | S3 Raw 객체 기반 도메인 전처리 및 DynamoDB 적재 Lambda handler |
| `src/kr_details_pipeline/cli.py` | `domain-preprocess` 로컬 CLI 엔트리포인트 |

## 4. 도메인 분류 및 적재 계약

### 4.1 분류 기준

| 조건 | 전처리 결과 |
| --- | --- |
| `contenttypeid == 39` | `restaurant` |
| `contenttypeid == 15` 또는 `festivals` 배열 원천 | `festival` |
| `contenttypeid == 12`, `14`, `28` | `attraction` |
| 허용되지 않은 content type | `review` 산출물로 분리 |
| `contentid` 또는 `title` 누락 | `failed` 산출물로 분리 |

### 4.2 DynamoDB key 규칙

| entity type | PK | SK |
| --- | --- | --- |
| city metadata | `CITY#{city_name_en}` | `METADATA#city` |
| restaurant | `CITY#{city_name_en}` | `RESTAURANT#{contentid}` |
| attraction | `CITY#{city_name_en}` | `ATTRACTION#{contentid}` |
| festival | `CITY#{city_name_en}` | `FESTIVAL#{contentid}` |
| visitor statistics | `CITY#{city_name_en}` | `STAT#{yyyymm}` |

도시별 산출물은 `PK = CITY#{city_name_en}` 기준으로 생성된다. 예를 들어 안동은 `PK = CITY#Andong`으로 생성된다.

## 5. 산출물 현황

현재 운영 적재 기준은 S3 Raw 전체 40개 파일과 `TourKoreaDomainData` 테이블이다.

| 항목 | 값 |
| --- | ---: |
| Raw S3 prefix | `raw/KR/details/20260609/` |
| 처리 파일 수 | 40 |
| Lambda | `kr-domain-loader` |
| DynamoDB table | `TourKoreaDomainData` |
| 성공 파일 수 | 40 |
| 부분 성공 파일 수 | 0 |
| 실패 파일 수 | 0 |
| 최종 DynamoDB item 수 | 4,334 |

안동 기준 로컬 산출물 예시는 다음과 같다.

| 산출물 | 파일 | 건수 |
| --- | --- | ---: |
| 도시 메타데이터 | `normalized/city_metadata.jsonl` | 1 |
| 음식점 | `normalized/restaurants.jsonl` | 26 |
| 관광지 | `normalized/attractions.jsonl` | 100 |
| 축제 | `normalized/festivals.jsonl` | 6 |
| 방문 통계 | `normalized/visitor_statistics.jsonl` | 12 |
| DynamoDB 적재 후보 | `load/tour_korea_domain_items.jsonl` | 145 |
| 검수 대상 | `review/domain_review.jsonl` | 0 |
| 실패 레코드 | `failed/invalid_records.jsonl` | 0 |

품질 요약은 `quality/summary.json`에 기록되며, 현재 결과는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| city_id | `KR-Andong` |
| city_name_en | `Andong` |
| table_name | `TourKoreaDomainData` |
| city_metadata | 1 |
| restaurants | 26 |
| attractions | 100 |
| festivals | 6 |
| visitor_statistics | 12 |
| load_items | 145 |
| review | 0 |
| failed | 0 |

## 6. 산출 데이터 예시

### 6.1 Restaurant

- SK 예시: `RESTAURANT#2687882`
- entity_id 예시: `REST-2687882`
- 주요 컬럼: `restaurant_category`, `cuisine_tags`, `phone`, `opening_hours`, `closed_days`, `signature_menu`, `parking`
- 확인 내용: 음식점 전용 컬럼만 유지되고 축제 날짜 컬럼은 포함되지 않는다.

### 6.2 Attraction

- SK 예시: `ATTRACTION#126157`
- entity_id 예시: `ATT-126157`
- 주요 컬럼: `theme`, `theme_tags`, `phone`, `opening_hours`, `closed_days`, `experience_guide`, `parking`, `season_tags`
- 확인 내용: 관광지 전용 운영 정보와 테마 정보가 분리되어 저장된다.

### 6.3 Festival

- SK 예시: `FESTIVAL#4060101`
- entity_id 예시: `FEST-4060101`
- 주요 컬럼: `event_start_date`, `event_end_date`, `month`, `season`, `season_tags`, `visit_months`, `venue`, `organizer`, `fee_text`
- 확인 내용: 축제 기간이 ISO 날짜와 월·계절 파생 필드로 정규화된다.

## 7. 품질 및 검수 결과

현재 안동 기준 산출물에서는 `review`와 `failed`가 모두 0건이며, 전체 S3 Raw 40개 파일의 Lambda 적재도 모두 `statusCode = 200`, `load_failed = 0`으로 완료되었다.

이는 다음 조건을 만족했다는 의미다.

- 핵심 식별자인 `contentid`, `title` 기반 item 생성 가능
- 도메인 분류 대상 content type이 허용 범위 안에 있음
- 도메인별 projection 이후 DynamoDB 후보 item 생성 가능
- 방문 통계 12개월 항목이 `STAT#{yyyymm}` 형태로 분리 가능

전체 재적재 결과 기준으로 DynamoDB write 실패는 확인되지 않았다. 단, 도메인별 품질 리뷰 기준은 서비스 요구사항이 확정될 때 추가 검증할 수 있다.

## 8. 검증 현황

현재 확인된 테스트와 검증 범위는 다음과 같다.

| 검증 항목 | 상태 |
| --- | --- |
| `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m pytest src` | 13 passed |
| `src/kr_details_pipeline/tests/test_transform.py` | Transform 기본 분기, 좌표 review, 방문월 파생 테스트 통과 |
| `src/kr_details_pipeline/tests/test_load.py` | DynamoDB put helper 기본 테스트 통과 |
| 안동 전처리 산출물 건수 확인 | 완료 |
| review/failed 0건 확인 | 완료 |
| 도메인별 샘플 item 구조 확인 | 완료 |
| 전체 KR 40개 도시 일괄 전처리 | 완료 |
| S3 Raw 40개 파일 Lambda 재적재 | 완료: 40 success, 0 partial, 0 failed |
| DynamoDB 최종 item 수 확인 | 완료: 4,334 |
| domain-preprocess 전용 단위 테스트 | 보강 필요 |
| 실제 DynamoDB write end-to-end 검증 | 완료: `kr-domain-loader` 수동 실행 기준 |

## 9. 현재 리스크

1. 기존 `TourKoreaData`와 신규 `TourKoreaDomainData`의 역할이 문서상 명확히 분리되어야 한다.
   - 현재 도메인 분리 적재의 운영 기준은 `TourKoreaDomainData`이다.
   - 기존 `TourKoreaData`는 이전 파이프라인 호환 또는 비교용 테이블로 남아 있다.
   - README와 관련 문서에서 두 테이블의 사용 목적을 명확히 분리해야 한다.

2. `domain-preprocess` 운영 명령이 README에 아직 반영되지 않았다.
   - CLI에는 명령이 존재하지만 팀원이 바로 실행할 수 있는 문서 섹션은 부족하다.

3. 실제 S3 Raw ingest manifest는 현재 비어 있다.
   - `data/KR/ingest/raw_manifest.json` 기준 `record_count = 0`이다.
   - 로컬 파일 기반 전처리와 S3 Raw 기반 운영 실행 상태를 분리해서 관리해야 한다.

4. 전용 테스트 보강이 필요하다.
   - 음식점/관광지/축제 projection allowlist 테스트
   - 제외 content type review 분리 테스트
   - `contentid` 또는 `title` 누락 failed 분리 테스트
   - `domain_loader_handler`의 부분 실패 응답 테스트

5. uv 전역 캐시 권한 이슈가 있다.
   - `uv run python -m pytest src`를 그대로 실행하면 현재 환경에서 사용자 전역 uv cache 접근 권한 오류가 발생한다.
   - README의 안내처럼 `$env:UV_CACHE_DIR='.cache\uv'`를 지정하면 정상 실행된다.

## 10. 권장 다음 작업

1. domain-preprocess 테스트 추가
   - `src/kr_details_pipeline/tests/test_domain_preprocess.py` 추가
   - 도메인 분류, projection allowlist, quality 분기, output writer를 단위 검증

2. README 명령 보강
   - `domain-preprocess` 로컬 실행 예시 추가
   - 산출물 경로와 review/failed 확인 명령 추가
   - `kr-domain-loader` 전체 재적재 절차 추가

3. S3 Raw ingest manifest 정리
   - Raw ingest manifest가 실제 S3 업로드 결과를 담도록 실행
   - S3 raw prefix와 DynamoDB 적재 이력을 연결하는 운영 기록 방식 확정

4. 실패 경로 검증
   - DynamoDB write 실패 시 `statusCode = 207`과 failures payload가 정상 반환되는지 확인
   - 일부 파일 실패 시 재시도 범위와 삭제 범위 문서화

## 11. 결론

현재 기준으로 KR 상세 Raw 데이터의 도메인 전처리 구조는 S3 Raw 40개 도시 전체에서 정상 적재되었다. `TourKoreaDomainData`는 전체 삭제 후 재적재되었고, `kr-domain-loader` 기준 40개 파일 모두 `statusCode = 200`, `load_failed = 0`으로 완료되었다. 최종 DynamoDB item 수는 4,334건이다.

다음 단계는 domain-preprocess 전용 테스트 추가, README 실행 문서 보강, S3 Raw ingest manifest 정리, 실패 경로 검증이다. 이 네 가지가 완료되면 KR 상세 데이터 전처리 라인은 반복 운영 가능한 수동 적재 단계로 넘길 수 있다.
