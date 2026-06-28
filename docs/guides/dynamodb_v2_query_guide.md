# DynamoDB TourKoreaDomainDataV2 Query 사용 가이드

이 문서는 2026-06-28 live AWS 조회 기준의 `TourKoreaDomainDataV2` 운영 조회 방법을 정리한다.

## 테이블 개요

| 항목 | 값 |
|---|---|
| 테이블 이름 | `TourKoreaDomainDataV2` |
| AWS account / region | `925273580929` / `us-east-1` |
| 총 아이템 | 9,778 |
| 테이블 크기 | 16,121,890 bytes |
| 과금 모드 | PAY_PER_REQUEST |
| PITR | 활성화, 35일 |

## 현재 적재 상태

| entity_type | 아이템 수 | 비고 |
|---|---:|---|
| `city_metadata` | 211 | 도시 메타데이터 |
| `attraction` | 6,335 | 관광지 |
| `festival` | 328 | 축제 |
| `visitor_statistics` | 2,904 | 242개 도시 x 2025년 12개월 |
| **합계** | **9,778** | live scan count |

현재 라이브 샘플에서 `CITY#GANGNEUNG`은 131건, `CITY#Gangneung`은 0건이다. `visitor_statistics`도 다른 도메인과 동일하게 대문자 `CITY#{영문 도시키}`를 사용한다.

## 연결 리소스

| 리소스 | 현재 상태 |
|---|---|
| Raw S3 | `s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260625/` 211 objects, 27,536,569 bytes |
| Processed summary | `s3://lovv-data-pipeline-dev-925273580929/processed/KR/domain/20260625/` 211 summary objects |
| Image S3 | `s3://lovv-pipeline-images-dev-925273580929/images/KR/` 9,163 objects, 2,645,146,287 bytes |
| S3 Vector | `lovv-vector-dev/kr-tour-domain-v1`, 7,073 vectors, float32 1024 dim cosine |
| Legacy table | `TourKoreaDomainData`도 ACTIVE이며 8,022 items가 남아 있다. 신규 운영 조회는 V2를 우선한다. |
| Deployed Lambda default | `kr-pipeline-transform`, `kr-pipeline-loader`, `kr-pipeline-vector`의 기본 `DYNAMODB_TABLE` 환경변수는 `TourKoreaDomainData`이다. V2 기준 실행은 payload `table_name=TourKoreaDomainDataV2` 등 명시적 override를 확인한다. |

## 키 스키마

| 키 | 타입 | 설명 | 예시 |
|---|---|---|---|
| PK (Hash) | String | `CITY#{영문 도시키}` | `CITY#GANGNEUNG`, `CITY#JONGNO-GU` |
| SK (Range) | String | 엔티티별 SK | `METADATA#city`, `ATTRACTION#12345`, `FESTIVAL#67890`, `STAT#202501` |

한글 도시명에서 PK suffix를 찾을 때는 `data/KR/city_name_en_lookup.json`의 매핑을 기준으로 한다.

## Entity Types

| entity_type | SK 패턴 | 설명 |
|---|---|---|
| city_metadata | `METADATA#city` | 도시 메타데이터 |
| attraction | `ATTRACTION#{content_id}` | 관광지 |
| festival | `FESTIVAL#{content_id}` | 축제 |
| visitor_statistics | `STAT#{YYYYMM}` | 월별 방문자 통계 |

## GSI

| GSI 이름 | Hash Key | Range Key | 용도 |
|---|---|---|---|
| `CityDomainIndex` | city_key | domain_sort_key | 도시별 전체 데이터 |
| `ProvinceDomainIndex` | province_key | domain_sort_key | 광역시/도별 조회 |
| `EntityTypeDomainIndex` | entity_type | domain_sort_key | 타입별 전체 조회 |
| `FestivalMonthIndex` | entity_type | gsi_sk | 월별 축제 |

`visitor_statistics`는 `gsi_sk`를 갖지 않으므로 `FestivalMonthIndex`에 포함되지 않는다.

## Query 패턴

### 1. 특정 도시의 모든 데이터

```python
import boto3
from boto3.dynamodb.conditions import Key

table = boto3.resource('dynamodb').Table('TourKoreaDomainDataV2')

response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG')
)
items = response['Items']
print(f"강릉 전체 아이템: {len(items)}")
```

### 2. 도시의 관광지만 조회

```python
response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG') & Key('SK').begins_with('ATTRACTION#')
)
attractions = response['Items']
```

### 3. 도시의 축제만 조회

```python
response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG') & Key('SK').begins_with('FESTIVAL#')
)
festivals = response['Items']
```

### 4. 도시의 방문자 통계 조회

```python
response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG') & Key('SK').begins_with('STAT#')
)
stats = response['Items']
# 월별 통계: stats[0]['statistics']['locals_total'], etc.
```

### 5. 특정 entity_type 전체 조회 (GSI)

```python
response = table.query(
    IndexName='EntityTypeDomainIndex',
    KeyConditionExpression=Key('entity_type').eq('attraction')
)
all_attractions = response['Items']
# 주의: 페이지네이션 필요 (LastEvaluatedKey)
```

### 6. 특정 월의 축제 조회 (GSI)

```python
response = table.query(
    IndexName='FestivalMonthIndex',
    KeyConditionExpression=Key('entity_type').eq('festival') & Key('gsi_sk').begins_with('FESTIVAL#07')
)
july_festivals = response['Items']
```

## AWS CLI 예시

예시는 로컬 기본 profile이 설정되어 있지 않은 경우를 위해 `--profile skn26_final --region us-east-1`을 포함한다.

```bash
# 도시 아이템 수
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk":{"S":"CITY#GANGNEUNG"}}' \
  --select COUNT \
  --profile skn26_final --region us-east-1

# 전체 attraction 수 (GSI)
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --index-name EntityTypeDomainIndex \
  --key-condition-expression "entity_type = :et" \
  --expression-attribute-values '{":et":{"S":"attraction"}}' \
  --select COUNT \
  --profile skn26_final --region us-east-1

# 방문자 통계 조회
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \
  --expression-attribute-values '{":pk":{"S":"CITY#GANGNEUNG"},":sk":{"S":"STAT#"}}' \
  --projection-expression "SK,city_name_ko,city_name_en,province_key,statistics" \
  --profile skn26_final --region us-east-1
```

## 방문자 통계 필드 구조

```json
{
  "PK": "CITY#JONGNO-GU",
  "SK": "STAT#202507",
  "entity_type": "visitor_statistics",
  "city_key": "CITY#JONGNO-GU",
  "city_name_ko": "종로구",
  "city_name_en": "JONGNO-GU",
  "province": "서울특별시",
  "province_key": "PROVINCE#서울특별시",
  "domain_sort_key": "STAT#202507",
  "month": "202507",
  "statistics": {
    "month": "202507",
    "days": 31,
    "locals_total": 523456.0,
    "locals_daily_avg": 16885.7,
    "out_of_town_total": 312000.0,
    "out_of_town_daily_avg": 10064.5,
    "foreigners_total": 89000.0,
    "foreigners_daily_avg": 2871.0,
    "total_visitors": 924456.0,
    "total_daily_avg": 29821.2
  }
}
```

## Attraction 레코드 구조

```json
{
  "PK": "CITY#GANGNEUNG",
  "SK": "ATTRACTION#125417",
  "entity_type": "attraction",
  "entity_id": "A-125417",
  "content_id": "125417",
  "title": "정동진",
  "description": "해돋이 명소...",
  "theme_tags": ["자연", "해변"],
  "season_tags": ["여름", "겨울"],
  "visit_months": ["06", "07", "12", "01"],
  "latitude": 37.6908,
  "longitude": 129.0333,
  "address": "강원특별자치도 강릉시 강동면",
  "image_url": "http://tong.visitkorea.or.kr/...",
  "quality_status": "passed",
  "city_key": "CITY#GANGNEUNG",
  "province_key": "PROVINCE#강원특별자치도",
  "domain_sort_key": "ATTRACTION#125417"
}
```

## 주의사항

1. **PK 형식**: 모든 신규 운영 예시는 `CITY#{대문자 영문 도시키}` 형식을 사용한다. 예: `CITY#GANGNEUNG`.
2. **방문자 통계**: `visitor_statistics`는 `SK=STAT#{YYYYMM}`, `domain_sort_key=STAT#{YYYYMM}`를 사용하고 `gsi_sk`는 없다.
3. **FestivalMonthIndex**: 월별 축제 조회 전용이다. `visitor_statistics`는 이 GSI에 포함되지 않는다.
4. **페이지네이션**: GSI 쿼리 시 `LastEvaluatedKey`로 반복 조회 필요
5. **visitor_statistics 제외**: 벡터 인덱스에는 포함되지 않음 (should_vectorize에서 제외)
6. **Vector manifest 주의**: `processed/KR/vector/manifests/latest.json`은 현재 16개짜리 과거/테스트 manifest다. 현재 인덱스 총량은 `s3vectors list-vectors`로 확인한 7,073개를 기준으로 한다.
