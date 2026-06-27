# KR 전국 데이터 파이프라인 전처리 보고서

## 실행 요약

| 항목 | 값 |
|---|---|
| 실행 일시 | 2026-06-28 |
| 대상 데이터 | 전국 211개 도시 (20260625 수집) + 방문자 통계 242개 도시 |
| DynamoDB 테이블 | `TourKoreaDomainDataV2` |
| 벡터 인덱스 | `kr-tour-domain-v1` (lovv-vector-dev) |
| 이미지 버킷 | `lovv-pipeline-images-dev-925273580929` |

## 파이프라인 실행 결과

### 1단계: DynamoDB 적재 (Transform + Load)

| 메트릭 | 값 |
|---|---|
| 소스 | `raw/KR/details/20260625/` (211 파일, 27.5MB) |
| Lambda | `kr-pipeline-transform` |
| 적재 도시 수 | 211 |
| 총 아이템 적재 | 6,874 (attraction + festival + city metadata) |
| 실행 시간 | 35초 |
| 에러 | 0 |

### 2단계: 방문자 통계 수집 + 적재

| 메트릭 | 값 |
|---|---|
| API | TourAPI DataLabService `locgoRegnVisitrDDList` |
| 수집 도시 수 | 242개 시/군/구 |
| 기간 | 2025년 1~12월 (12개월) |
| 적재 아이템 | 2,904 (242 × 12개월) |
| 수집 시간 | ~60초 |
| 적재 시간 | ~5분 |

### 3단계: 이미지 처리 (S3 적재)

| 메트릭 | 값 |
|---|---|
| Lambda | `kr-pipeline-image` |
| 처리 도시 수 | 211 |
| 이미지 다운로드 성공 | 6,246 |
| 다운로드 실패 | 0 |
| 소스 이미지 없음 (review) | 402 |
| 이미지 총 용량 | ~1.2GB |
| 실행 시간 | 24분 (5 병렬) |

### 4단계: 벡터 인덱스 빌드

| 메트릭 | 값 |
|---|---|
| 소스 테이블 | `TourKoreaDomainDataV2` (EntityTypeDomainIndex GSI) |
| Export 아이템 | 9,108 |
| 생성 Chunks | 9,108 |
| 중복 제거 | 2,035 |
| 최종 벡터 수 | **7,073** |
| 임베딩 모델 | Amazon Titan Embed Text v2 (1024 dim) |
| 실행 시간 | 44분 |

## DynamoDB V2 최종 상태

| entity_type | 아이템 수 | 설명 |
|---|---|---|
| attraction | ~5,800 | 관광지 |
| festival | ~500 | 축제 |
| city (metadata) | 211 | 도시 메타데이터 |
| visitor_statistics | 2,904 | 월별 방문자 통계 (242도시 × 12개월) |
| **합계** | **9,778** | |

## 인프라 구성

### Lambda 함수

| Lambda | 역할 | 런타임 | 메모리 |
|---|---|---|---|
| `kr-pipeline-transform` | raw → DynamoDB 적재 | Python 3.12 | 512MB |
| `kr-pipeline-loader` | DynamoDB load + Vector build | Python 3.12 | 512MB |
| `kr-pipeline-vector` | Vector build standalone | Python 3.12 | 1024MB |
| `kr-pipeline-image` | 이미지 다운로드 + S3 적재 | Python 3.12 | 512MB |

### Step Functions

| 항목 | 값 |
|---|---|
| 상태 머신 | `kr-data-pipeline-dev` |
| 흐름 | Transform → Image → Load → Vector → Report |

### GSI (Global Secondary Index)

| GSI 이름 | Hash Key | Range Key | 용도 |
|---|---|---|---|
| CityDomainIndex | city_key | domain_sort_key | 도시별 조회 |
| ProvinceDomainIndex | province_key | domain_sort_key | 광역시/도별 조회 |
| EntityTypeDomainIndex | entity_type | domain_sort_key | 타입별 조회 (벡터 빌드) |
| FestivalMonthIndex | entity_type | gsi_sk | 월별 축제 조회 |

## 데이터 품질

| 항목 | 상태 |
|---|---|
| 중복 아이템 | ✅ 제거됨 (20260625 단일 소스만 사용) |
| 이미지 적재율 | 94% (6,246/6,648 이미지 보유 레코드) |
| 방문자 통계 커버리지 | 242/264 시군구 (92%) |
| 벡터화 대상 제외 | restaurant, visitor_statistics |
| 벡터 검색 정확도 | ✅ 의미 검색 정상 동작 확인 |
