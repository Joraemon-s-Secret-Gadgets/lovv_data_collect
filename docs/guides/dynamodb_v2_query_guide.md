# DynamoDB TourKoreaDomainDataV2 Query 사용 가이드

## 테이블 개요

| 항목 | 값 |
|---|---|
| 테이블 이름 | `TourKoreaDomainDataV2` |
| 총 아이템 | 9,778 |
| 과금 모드 | PAY_PER_REQUEST |
| PITR | 활성화 |

## 키 스키마

| 키 | 타입 | 설명 | 예시 |
|---|---|---|---|
| PK (Hash) | String | `CITY#{도시명}` | `CITY#GANGNEUNG`, `CITY#종로구` |
| SK (Range) | String | 엔티티별 SK | `METADATA#city`, `ATTRACTION#12345`, `FESTIVAL#67890`, `STAT#202501` |

## Entity Types

| entity_type | SK 패턴 | 설명 |
|---|---|---|
| city | `METADATA#city` | 도시 메타데이터 |
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
    KeyConditionExpression=Key('PK').eq('CITY#종로구') & Key('SK').begins_with('STAT#')
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

```bash
# 도시 아이템 수
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk":{"S":"CITY#GANGNEUNG"}}' \
  --select COUNT

# 전체 attraction 수 (GSI)
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --index-name EntityTypeDomainIndex \
  --key-condition-expression "entity_type = :et" \
  --expression-attribute-values '{":et":{"S":"attraction"}}' \
  --select COUNT

# 방문자 통계 조회
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \
  --expression-attribute-values '{":pk":{"S":"CITY#종로구"},":sk":{"S":"STAT#"}}' \
  --projection-expression "SK,statistics"
```

## 방문자 통계 필드 구조

```json
{
  "PK": "CITY#종로구",
  "SK": "STAT#202507",
  "entity_type": "visitor_statistics",
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
  "province_key": "강원특별자치도",
  "domain_sort_key": "attraction#125417",
  "gsi_sk": "attraction#125417"
}
```

## 주의사항

1. **PK 형식**: 20260625 데이터는 대문자 (`CITY#GANGNEUNG`), 방문자 통계는 한글 (`CITY#종로구`)
2. **페이지네이션**: GSI 쿼리 시 `LastEvaluatedKey`로 반복 조회 필요
3. **visitor_statistics 제외**: 벡터 인덱스에는 포함되지 않음 (should_vectorize에서 제외)
4. **restaurant 제외**: 벡터화 대상에서 제외됨
