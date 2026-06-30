# KR 데이터 취득 통합 보고서

## 1. 보고서 개요

| 항목 | 값 |
|---|---|
| 작성일 | 2026-06-29 |
| 대상 국가 | 대한민국 |
| 기준 데이터 | 2026-06-25 TourAPI raw detail 취득분 |
| 보정 데이터 | 2026-06-29 동명이구 및 odd key 보정 취득분 |
| 통합 기준 ingest date | `20260629` |
| S3 버킷 | `lovv-data-pipeline-dev-925273580929` |
| 보고 범위 | 0625 raw detail 기준 데이터 + 0629 보정분 병합, Wikipedia raw 업로드, DataLab local 병합, S3 raw 검증 |
| 제외 범위 | `processed/` 전처리, DynamoDB V2 적재, vector rebuild |

본 보고서는 2026-06-25에 취득된 KR TourAPI raw detail 데이터를 기준 데이터로 삼고, 2026-06-29에 확인된 동명이구 저장 키 충돌과 포항 odd key 문제를 보정한 뒤, 통합 결과를 `20260629` S3 raw prefix에 적재한 결과를 정리한다.

오늘 작업은 신규 전체 재취득이라기보다 **0625 기준 데이터에 대한 문제 보정 및 재업로드 트러블슈팅**으로 분류한다.

## 2. 최종 판단

`20260629` 통합 raw prefix는 0625 기준 데이터와 0629 보정분을 병합한 운영 후보 raw dataset으로 사용할 수 있다.

| 항목 | 결과 |
|---|---:|
| Wikipedia raw 업로드 객체 | 2 |
| TourAPI detail raw 업로드 객체 | 240 |
| TourAPI detail unique S3 key | 240 |
| 미해결 S3 key 충돌 | 0 |
| odd key (`_.json`) 잔존 | 0 |
| 원격 검증 `GOSEONG-GANGWON.json` | 존재 |
| 원격 검증 `POHANG.json` | 존재 |
| 원격 검증 `_.json` | 없음 |

다만 DataLab 방문통계는 local 병합까지 완료된 상태이며, 현재 S3 raw detail 객체 내부에는 내장되어 있지 않다. DataLab를 S3에 별도 raw 객체로 보관할지, detail raw에 내장할지는 후속 전처리/적재 설계에서 결정해야 한다.

## 3. 기준 데이터: 2026-06-25 TourAPI raw detail

0625 취득분은 기존 전국 TourAPI 관광지/문화시설/축제 raw detail의 기준선이다.

| 항목 | 값 |
|---|---:|
| 기준 보고서 | `docs/reports/kr_tour_api_data_acquisition_report_20260625.md` |
| S3 prefix | `raw/KR/details/20260625/` |
| 상세 JSON 파일 수 | 211 |
| 포함 광역시/도 수 | 17 |
| 최종 수집 콘텐츠 수 | 6,663 |
| 관광지/문화시설 계열 | 6,335 |
| 축제/행사 계열 | 328 |
| 빈 산출물 파일 | 5 |
| S3 upload status | uploaded 211, failed 0, skipped 0 |
| 업로드 바이트 | 27,536,569 bytes |

0625 기준 데이터는 raw detail 취득 자체는 완료되었지만, 이후 분석에서 다음 문제가 확인되었다.

1. `중구`, `동구`, `서구`, `남구`, `북구`, `강서구`, `고성군` 등 동명이구가 standalone display name 기반 저장 키로 수렴할 수 있다.
2. 일부 파일은 파일명과 실제 행정구역 metadata가 불일치할 수 있다.
3. 0625 raw detail에는 DataLab 방문통계가 내장되어 있지 않다.

따라서 0625 prefix는 참조 및 rollback 기준으로 보존하고, 운영 후보 raw는 0629 보정 prefix로 분리했다.

## 4. 보정 데이터: 2026-06-29 overlay

0629 작업은 0625 기준 데이터 위에 다음 보정분을 얹는 방식으로 수행했다.

| 항목 | 값 |
|---|---:|
| 오늘 재취득한 동명이구 detail 파일 | 29 |
| local detail 입력 파일 | 241 |
| S3 업로드 선별 파일 | 240 |
| S3 unique key | 240 |
| 선별 파일 총 attraction 수 | 8,224 |
| 선별 파일 총 festival 수 | 400 |
| 선별 파일 총 크기 | 35,156,793 bytes |
| resolved conflict | 1 |
| unresolved conflict | 0 |
| odd key count | 0 |

통합 raw 업로드 대상 prefix:

```text
raw/KR/details/20260629/{city_key}.json
```

`20260629` prefix는 0625 기준 데이터와 오늘 보정분을 병합한 새 ingest date이다. 기존 `20260625` prefix를 제자리 갱신하지 않은 이유는 비교, rollback, 전처리 재실행 기준을 분리하기 위해서다.

## 5. Wikipedia 및 DataLab 병합 현황

### 5.1 Wikipedia 도시 메타데이터

| 항목 | 값 |
|---|---:|
| `data/KR/cities.json` 도시 수 | 229 |
| `data/KR/prefectures.json` 광역시/도 수 | 17 |
| S3 업로드 객체 | 2 |

업로드 대상:

| local path | S3 key | status |
|---|---|---|
| `data/KR/cities.json` | `raw/KR/wikipedia/20260629/cities.json` | uploaded |
| `data/KR/prefectures.json` | `raw/KR/wikipedia/20260629/prefectures.json` | uploaded |

### 5.2 TourAPI DataLab 2025 방문통계

| 항목 | 값 |
|---|---:|
| local 병합 파일 | `data/KR/visitor_statistics_2025.json` |
| 도시 키 수 | 271 |
| 월별 레코드 수 | 3,252 |
| 도시별 월 개수 | 12 |
| 기간 | 2025-01 ~ 2025-12 |

DataLab는 2025년 월별 방문통계를 기준으로 병합되었다. 이번 작업에서는 기존에 누락 또는 병합 충돌로 보였던 동명이구 대상에 대한 DataLab 취득분을 기존 local 통계 파일에 병합했다.

주의: 현재 S3 detail raw 업로드 readiness에서 `visitor_statistics_count`는 0으로 집계된다. 즉, 방문통계는 local 통계 파일에 병합되어 있으며, detail raw 파일 내부에 내장된 형태로 S3에 올라간 상태는 아니다.

## 6. S3 업로드 및 원격 검증

사용자 요청에 따라 raw AWS CLI 직접 업로드 대신 repository upload code path를 사용했다.

| 대상 | 사용 경로 |
|---|---|
| Wikipedia raw | `crawling.KR.s3_uploader.upload_crawl_results()` |
| TourAPI detail raw | `src/kr_details_pipeline` raw ingest/upload path |

업로드 결과:

| 대상 | status | count |
|---|---|---:|
| Wikipedia raw | uploaded | 2 |
| TourAPI detail raw | uploaded | 240 |

검증 파일:

```text
data/KR/ingest/20260629_wikipedia_upload_results.json
data/KR/ingest/20260629_resolved_details/raw_manifest.json
data/KR/ingest/20260629_resolved_details/upload_results.jsonl
data/KR/ingest/20260629_s3_verification.json
```

원격 검증 결과:

| 항목 | 값 |
|---|---:|
| `wiki_count` | 2 |
| `detail_count` | 240 |
| `detail_unique_count` | 240 |
| `has_goseong_gangwon` | true |
| `has_pohang` | true |
| `has_underscore` | false |

검증된 Wikipedia keys:

```text
raw/KR/wikipedia/20260629/cities.json
raw/KR/wikipedia/20260629/prefectures.json
```

## 7. 2026-06-29 Troubleshooting

### 7.1 문제: 동명이구 저장 키 충돌

#### 증상

TourAPI API 요청은 `lDongRegnCd`, `lDongSignguCd`를 사용해 지역을 구분하지만, 저장 단계에서 standalone `city_name_en` 또는 표시명 기반 파일명이 사용되면 같은 이름의 시군구가 같은 파일명으로 수렴할 수 있다.

영향 그룹:

| 시군구명 | 대상 수 |
|---|---:|
| 강서구 | 2 |
| 고성군 | 2 |
| 남구 | 4 |
| 동구 | 6 |
| 북구 | 4 |
| 서구 | 5 |
| 중구 | 6 |

총 7개 이름 그룹, 29개 대상이 영향을 받는다.

#### 대응

29개 동명이구 대상에 대해 오늘 취득분을 생성하고, S3 업로드 전 readiness 단계에서 `city_key` 기준으로 key 중복을 확인했다.

#### 결과

최종 upload 대상은 240개 unique S3 key로 정리되었고, 미해결 충돌은 0건이다.

### 7.2 문제: 고성군 `GOSEONG-GANGWON.json` 충돌

#### 증상

S3 readiness 검증에서 아래 key에 대해 1건의 충돌이 확인되었다.

| S3 key | 충돌 후보 |
|---|---|
| `raw/KR/details/20260629/GOSEONG-GANGWON.json` | `KR-42-GOSEONG-GANGWON.json`, `goseong-gangwon.json` |

#### 사용자 결정

오늘 날짜로 취득한 데이터를 신뢰 가능한 데이터로 취급한다.

#### 대응 결과

| 선택 파일 | 제외 파일 | 정책 |
|---|---|---|
| `KR-42-GOSEONG-GANGWON.json` | `goseong-gangwon.json` | `prefer_today_reacquired_city_id_file` |

최종 readiness:

| 항목 | 값 |
|---|---:|
| resolved conflict | 1 |
| unresolved conflict | 0 |

### 7.3 문제: 포항 odd key `_.json`

#### 증상

`포항시 남구` 계열 산출물에서 `_.json`, `__filtered.json` 형태의 odd key가 확인되었다. 이 key는 S3 raw key로 그대로 올라가면 추적성과 전처리 key 정합성을 해친다.

#### 사용자 결정

포항으로 합친다.

#### 대응 결과

| 원본 | 병합 대상 |
|---|---|
| `data/KR/details/_.json` | `data/KR/details/pohang.json` |
| `data/KR/raw_tour_api/__filtered.json` | `data/KR/raw_tour_api/pohang_filtered.json` |

원본 보존 경로:

```text
data/KR/merged_sources_20260629/pohang/details/_.json
data/KR/merged_sources_20260629/pohang/raw_tour_api/__filtered.json
```

원격 검증 결과:

| key | 결과 |
|---|---|
| `raw/KR/details/20260629/POHANG.json` | 존재 |
| `raw/KR/details/20260629/_.json` | 없음 |

### 7.4 문제: DataLab 누락처럼 보인 22개 대상

#### 증상

초기 보고에서는 DataLab 방문통계가 API에서 잡히지 않는 시군구가 존재하는 것으로 보였다.

#### 분석

실제 원인은 API 무응답만이 아니라, `중구`, `동구`, `서구`처럼 이름이 같은 시군구를 standalone 이름으로 다룰 때 병합 기준이 겹치는 문제였다.

#### 대응 결과

동명이구 29개 대상의 DataLab 2025 월별 통계를 재취득해 local `visitor_statistics_2025.json`에 병합했다. 최종 local 통계 파일은 271개 도시 키와 3,252개월 레코드를 가진다.

### 7.5 문제: 업로드 방식

#### 증상

초기에는 S3 직접 업로드 방식도 가능했지만, 사용자 요청은 repository S3 업로드 코드를 사용하는 것이었다.

#### 대응 결과

다음 코드 경로로 업로드했다.

| 대상 | 코드 경로 |
|---|---|
| Wikipedia raw | `crawling.KR.s3_uploader.upload_crawl_results()` |
| TourAPI detail raw | `src/kr_details_pipeline` raw ingest/upload path |

## 8. 현재 리스크와 후속 작업

1. **전처리 Spec 분리**
   - 취득 라인은 `raw/KR/details/20260629/{city_key}.json`까지로 정리한다.
   - `processed/KR/details/{ingest_date}/passed/`, DynamoDB V2 PK/SK, vector rebuild는 전처리 Spec에서 다룬다.

2. **DataLab S3 raw 보관 방식 결정**
   - 현재 DataLab는 local 병합 완료 상태다.
   - S3에는 detail raw 내부 내장 형태로 올라간 상태가 아니다.
   - 별도 `raw/KR/datalab/{ingest_date}/visitor_statistics_2025.json` 같은 경로를 둘지 결정이 필요하다.

3. **Wikipedia metadata와 TourAPI detail object 수 정합성**
   - Wikipedia 도시 metadata는 229개다.
   - `20260629` detail raw upload object는 240개다.
   - 전처리 전 `city_key`/`city_id` 기준 reconciliation 검증이 필요하다.

4. **기존 prefix 병행 관리**
   - `raw/KR/details/20260625/`는 최초 기준선 및 rollback용으로 보존한다.
   - `raw/KR/details/20260629/`는 보정 반영 운영 후보 raw prefix로 사용한다.

## 9. 다음 실행 기준

전처리 단계는 다음 입력을 기준으로 실행한다.

```text
s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260629/
s3://lovv-data-pipeline-dev-925273580929/raw/KR/wikipedia/20260629/
```

전처리 산출물은 아래 prefix로 분리하는 것이 적절하다.

```text
processed/KR/details/20260629/passed/
processed/KR/details/20260629/review/
processed/KR/details/20260629/failed/
processed/KR/details/20260629/quality/
```

`passed/` prefix만 DynamoDB V2 적재와 vector rebuild 입력으로 넘긴다.
