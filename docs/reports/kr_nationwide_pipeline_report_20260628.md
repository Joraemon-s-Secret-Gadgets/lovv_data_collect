# KR 전국 데이터 파이프라인 전처리 보고서

## 실행 요약

| 항목 | 값 |
|---|---|
| 실행 일시 | 2026-06-28 |
| AWS 재조회 기준 | 2026-06-28 live read, `us-east-1`, account `925273580929` |
| 대상 데이터 | 전국 211개 도시 (20260625 수집) + 방문자 통계 242개 도시 |
| DynamoDB 테이블 | `TourKoreaDomainDataV2` |
| 벡터 인덱스 | `kr-tour-domain-v1` (lovv-vector-dev) |
| 이미지 버킷 | `lovv-pipeline-images-dev-925273580929` |

## 파이프라인 실행 결과

### 1단계: DynamoDB 적재 (Transform + Load)

| 메트릭 | 값 |
|---|---|
| 소스 | `raw/KR/details/20260625/` (211 objects, 27,536,569 bytes) |
| 처리 산출물 | `processed/KR/domain/20260625/` (211 summary objects, 105,857 bytes) |
| Lambda | `kr-pipeline-transform` |
| 적재 도시 수 | 211 |
| 총 아이템 적재 | 6,874 (attraction + festival + city metadata) |
| 라이브 테이블 총량 | `TourKoreaDomainDataV2` 9,778 items |
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
| 현재 이미지 prefix | `s3://lovv-pipeline-images-dev-925273580929/images/KR/` |
| 현재 이미지 객체 수 | 9,163 |
| 현재 이미지 총 용량 | 2,645,146,287 bytes (~2.46 GiB) |
| 강릉 prefix 샘플 | 92 objects, 22,587,039 bytes |
| 산출물 성격 | 라이브 S3 버킷 누적 상태 |
| 최신 실행별 성공/실패 manifest | `processed/KR/report/`, `processed/KR/reports/`에서 확인되지 않음 |

### 4단계: 벡터 인덱스 빌드

| 메트릭 | 값 |
|---|---|
| 소스 테이블 | `TourKoreaDomainDataV2` (EntityTypeDomainIndex GSI) |
| 라이브 벡터 수 | **7,073** (`s3vectors list-vectors` 기준) |
| 인덱스 설정 | float32, 1024 dim, cosine, SSE-S3 AES256 |
| 임베딩 모델 | Amazon Titan Embed Text v2 (1024 dim) |
| 최신 manifest 주의 | `processed/KR/vector/manifests/latest.json`은 2026-06-23 16개 테스트/과거 manifest로, 현재 총량 근거로 사용하지 않음 |

## DynamoDB V2 최종 상태

| entity_type | 아이템 수 | 설명 |
|---|---|---|
| attraction | 6,335 | 관광지 |
| festival | 328 | 축제 |
| city_metadata | 211 | 도시 메타데이터 |
| visitor_statistics | 2,904 | 월별 방문자 통계 (242도시 × 12개월) |
| **합계** | **9,778** | |

2026-06-28 보정 이후 `visitor_statistics`의 PK도 `CITY#{영문 도시키}` 형식으로 정리되었다. 라이브 샘플 조회에서 `CITY#GANGNEUNG`은 131건, `CITY#Gangneung`은 0건이므로 운영 예시는 대문자 영문 도시키를 사용해야 한다.

## 인프라 구성

### Lambda 함수

| Lambda | 역할 | 런타임 | 메모리 |
|---|---|---|---|
| `kr-pipeline-transform` | raw → DynamoDB 적재 | Python 3.12 | 512MB / 300s |
| `kr-pipeline-loader` | DynamoDB load + Vector build | Python 3.12 | 512MB / 900s |
| `kr-pipeline-vector` | Vector build standalone | Python 3.12 | 1024MB / 900s |
| `kr-pipeline-image` | 이미지 다운로드 + S3 적재 | Python 3.12 | 512MB / 900s |

AWS Lambda 환경변수의 기본 `DYNAMODB_TABLE`은 2026-06-28 조회 시점에도 `TourKoreaDomainData`로 남아 있다. `TourKoreaDomainDataV2` 기준 실행은 loader/vector payload의 `table_name` 지정 또는 별도 V2 실행 경로를 명시해야 한다.

### Step Functions

| 항목 | 값 |
|---|---|
| 상태 머신 | `kr-data-pipeline-dev` |
| 흐름 | Transform → Image → Load → Vector → Report |
| 상태 | ACTIVE |
| 실행 이력 | `list-executions` 조회 결과 현재 반환된 실행 없음 |
| Transform/Image 병렬도 | 각 Map state `MaxConcurrency=10` |

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
| 이미지 버킷 상태 | 9,163 objects / 약 2.46 GiB 적재 확인 |
| 방문자 통계 커버리지 | 242/264 시군구 (92%) |
| 벡터화 대상 제외 | visitor_statistics |
| 벡터 인덱스 상태 | 7,073 vectors, index ACTIVE 조회 가능 |

## AWS 재조회 증거

| 조회 항목 | 결과 |
|---|---|
| `sts get-caller-identity` | account `925273580929`, ARN `arn:aws:iam::925273580929:root` |
| `dynamodb describe-table TourKoreaDomainDataV2` | ACTIVE, PAY_PER_REQUEST, PITR enabled, 9,778 items, 16,121,890 bytes |
| `dynamodb scan --select COUNT TourKoreaDomainDataV2` | Count 9,778 |
| `EntityTypeDomainIndex` count | city_metadata 211, attraction 6,335, festival 328, visitor_statistics 2,904 |
| `s3api list-objects-v2 raw/KR/details/20260625/` | 211 objects, 27,536,569 bytes |
| `s3api list-objects-v2 processed/KR/domain/20260625/` | 211 summary objects, 105,857 bytes |
| `s3api list-objects-v2 images/KR/` | 9,163 objects, 2,645,146,287 bytes |
| `s3vectors get-index` | `lovv-vector-dev/kr-tour-domain-v1`, float32, 1024 dim, cosine, AES256 |
| `s3vectors list-vectors` | 7,073 vectors |
