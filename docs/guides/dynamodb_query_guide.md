# DynamoDB Query 참고 가이드

> 현재 운영 기준은 [dynamodb_v2_query_guide.md](dynamodb_v2_query_guide.md)입니다.
> 이 문서는 기존 조회 패턴을 빠르게 확인하기 위한 보조 문서입니다. 2026-06-28 live AWS 기준 운영 PK는 `CITY#GANGNEUNG`처럼 대문자 영문 도시키입니다.

## 테이블 스키마

| 키 | 이름 | 타입 | 설명 |
|---|---|---|---|
| PK (Hash) | PK | String | `CITY#{city_name_en}` 형식 |
| SK (Range) | SK | String | `METADATA#city`, `ATTRACTION#{content_id}`, `FESTIVAL#{content_id}` |

## GSI (Global Secondary Index)

| GSI 이름 | Hash Key | Range Key | 용도 |
|---|---|---|---|
| `CityDomainIndex` | city_key | domain_sort_key | 도시별 전체 데이터 조회 |
| `ProvinceDomainIndex` | province_key | domain_sort_key | 광역시/도별 전체 데이터 조회 |
| `EntityTypeDomainIndex` | entity_type | domain_sort_key | entity 타입별 전체 조회 (벡터 빌드용) |
| `FestivalMonthIndex` | entity_type | gsi_sk | 월별 축제 조회 |

## 기본 Query 패턴

### 1. 특정 도시의 모든 데이터 조회

```python
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TourKoreaDomainDataV2')

# PK로 직접 Query
response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG')
)
items = response['Items']
```

### 2. 도시의 관광지만 조회

```python
response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG') & Key('SK').begins_with('ATTRACTION#')
)
```

### 3. 도시의 축제만 조회

```python
response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG') & Key('SK').begins_with('FESTIVAL#')
)
```

### 4. 도시 메타데이터 조회

```python
response = table.query(
    KeyConditionExpression=Key('PK').eq('CITY#GANGNEUNG') & Key('SK').eq('METADATA#city')
)
city_metadata = response['Items'][0]
```

## GSI Query 패턴

### 5. 특정 entity_type의 모든 아이템 (벡터 빌드용)

```python
# EntityTypeDomainIndex GSI 사용
response = table.query(
    IndexName='EntityTypeDomainIndex',
    KeyConditionExpression=Key('entity_type').eq('attraction')
)
all_attractions = response['Items']
```

### 6. 특정 광역시/도의 모든 데이터

```python
# ProvinceDomainIndex GSI 사용
response = table.query(
    IndexName='ProvinceDomainIndex',
    KeyConditionExpression=Key('province_key').eq('PROVINCE#강원특별자치도')
)
```

### 7. 특정 월의 축제 목록

```python
# FestivalMonthIndex GSI 사용
response = table.query(
    IndexName='FestivalMonthIndex',
    KeyConditionExpression=Key('entity_type').eq('festival') & Key('gsi_sk').begins_with('FESTIVAL#07')  # 7월
)
july_festivals = response['Items']
```

## AWS CLI 예시

```bash
# 도시의 모든 아이템 수 확인
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

# 특정 도시의 관광지 목록 (title만)
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \
  --expression-attribute-values '{":pk":{"S":"CITY#GANGNEUNG"},":sk":{"S":"ATTRACTION#"}}' \
  --projection-expression "title,image_url" \
  --profile skn26_final --region us-east-1
```

## 레코드 필드 구조

### Attraction/Festival 레코드

```json
{
  "PK": "CITY#GANGNEUNG",
  "SK": "ATTRACTION#12345",
  "entity_type": "attraction",
  "entity_id": "A-12345",
  "content_id": "12345",
  "title": "정동진",
  "description": "해돋이 명소...",
  "theme_tags": ["자연", "해변"],
  "season_tags": ["여름", "겨울"],
  "visit_months": ["06", "07", "12", "01"],
  "latitude": 37.6908,
  "longitude": 129.0333,
  "address": "강원특별자치도 강릉시 강동면 정동진리",
  "image_url": "https://tong.visitkorea.or.kr/cms/resource/...",
  "quality_status": "passed"
}
```

### City Metadata 레코드

```json
{
  "PK": "CITY#GANGNEUNG",
  "SK": "METADATA#city",
  "entity_type": "city",
  "city_id": "KR-GANGNEUNG",
  "city_name_en": "GANGNEUNG",
  "city_name_ko": "강릉시",
  "province": "강원특별자치도"
}
```
