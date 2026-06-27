# AgentCore v1 - DynamoDB Query Guide

> 대상 테이블: `TourKoreaDomainData` (V1)
> 리전: `us-east-1`
> 대상 지역: 강원특별자치도, 경상북도 (40개 도시)

## 1. 테이블 스키마

| 키 | 속성명 | 설명 |
|----|--------|------|
| Partition Key | `PK` | `CITY#{city_name_en}` (예: `CITY#Andong`) |
| Sort Key | `SK` | 엔티티별 패턴 (아래 참조) |

### SK 패턴

| 엔티티 타입 | SK 형식 | 예시 |
|-------------|---------|------|
| 도시 메타데이터 | `METADATA#city` | `METADATA#city` |
| 관광지 | `ATTRACTION#{content_id}` | `ATTRACTION#126023` |
| 축제 | `FESTIVAL#{content_id}` | `FESTIVAL#2948110` |

## 2. GSI (Global Secondary Index)

| GSI | Hash Key | Range Key | 용도 |
|-----|----------|-----------|------|
| **GSI1** | `city_key` | `domain_sort_key` | 도시별 모든 엔티티 조회 |
| **GSI2** | `province_key` | `domain_sort_key` | 도(province)별 전체 조회 |
| **GSI3** | `entity_type` | `domain_sort_key` | 엔티티 타입별 전체 조회 |
| **FestivalMonthIndex** | `entity_type` | `gsi_sk` | 축제 월별 조회 |

## 3. 주요 속성

### 공통 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `PK` | S | `CITY#{city_name_en}` |
| `SK` | S | 엔티티별 sort key |
| `entity_type` | S | `city_metadata`, `attraction`, `festival` |
| `entity_id` | S | 엔티티 고유 ID |
| `content_id` | S | TourAPI content ID |
| `quality_status` | S | `passed` / `failed` |
| `city_key` | S | GSI1 해시키 (= PK) |
| `province_key` | S | GSI2 해시키 (`PROVINCE#강원특별자치도` 등) |
| `domain_sort_key` | S | `{entity_type}#{content_id}` |
| `gsi_sk` | S | FestivalMonthIndex용 |

### 관광지(attraction) 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `title` | S | 관광지 이름 |
| `description` | S | 설명 |
| `theme` | S | 테마 (예: `history`, `nature`) |
| `theme_tags` | L | 테마 태그 배열 |
| `season_tags` | L | 시즌 태그 |
| `address` | S | 주소 |
| `latitude` | N | 위도 |
| `longitude` | N | 경도 |
| `image_url` | S | 대표 이미지 URL |
| `phone` | S | 전화번호 |
| `metadata_enrichment` | M | Bedrock 메타데이터 enrichment 결과 |
| `indoor_outdoor` | S | 실내/실외 구분 |
| `vibe_tags` | L | 분위기 태그 |
| `experience_tags` | L | 경험 태그 |
| `companion_fit` | L | 동행 적합성 |

### 축제(festival) 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `title` | S | 축제 이름 |
| `description` | S | 설명 |
| `eventstartdate` | S | 시작일 (YYYYMMDD) |
| `eventenddate` | S | 종료일 (YYYYMMDD) |
| `month` | S | 개최 월 (01~12) |
| `season` | S | 계절 |
| `festival_theme_classification` | M | 축제 테마 분류 결과 |

### 도시 메타데이터(city_metadata) 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `city_id` | S | 도시 ID (예: `KR-42-001`) |
| `city_name_en` | S | 영문명 |
| `city_name_ko` | S | 한글명 |
| `province` | S | 도/광역시명 |

## 4. Query 패턴 및 예시

### 4.1 특정 도시의 모든 데이터 조회 (기본 테이블)

```python
import boto3
from boto3.dynamodb.types import TypeDeserializer

session = boto3.Session(profile_name="skn26_final", region_name="us-east-1")
ddb = session.client("dynamodb")
td = TypeDeserializer()

resp = ddb.query(
    TableName="TourKoreaDomainData",
    KeyConditionExpression="PK = :pk",
    ExpressionAttributeValues={
        ":pk": {"S": "CITY#Andong"},
    },
)

items = [{k: td.deserialize(v) for k, v in item.items()} for item in resp["Items"]]
print(f"안동시 전체 아이템: {len(items)}건")
```

### 4.2 특정 도시의 관광지만 조회

```python
resp = ddb.query(
    TableName="TourKoreaDomainData",
    KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
    ExpressionAttributeValues={
        ":pk": {"S": "CITY#Andong"},
        ":sk_prefix": {"S": "ATTRACTION#"},
    },
)
```

### 4.3 특정 도시의 축제만 조회

```python
resp = ddb.query(
    TableName="TourKoreaDomainData",
    KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
    ExpressionAttributeValues={
        ":pk": {"S": "CITY#Gangneung"},
        ":sk_prefix": {"S": "FESTIVAL#"},
    },
)
```

### 4.4 도(province)별 전체 조회 — GSI2

```python
# 강원도 전체 데이터
resp = ddb.query(
    TableName="TourKoreaDomainData",
    IndexName="GSI2",
    KeyConditionExpression="province_key = :pk",
    ExpressionAttributeValues={
        ":pk": {"S": "PROVINCE#강원특별자치도"},
    },
)

# 경상북도 전체 데이터
resp = ddb.query(
    TableName="TourKoreaDomainData",
    IndexName="GSI2",
    KeyConditionExpression="province_key = :pk",
    ExpressionAttributeValues={
        ":pk": {"S": "PROVINCE#경상북도"},
    },
)
```

### 4.5 엔티티 타입별 조회 — GSI3

```python
# 모든 관광지
resp = ddb.query(
    TableName="TourKoreaDomainData",
    IndexName="GSI3",
    KeyConditionExpression="entity_type = :et",
    ExpressionAttributeValues={
        ":et": {"S": "attraction"},
    },
)

# 모든 축제
resp = ddb.query(
    TableName="TourKoreaDomainData",
    IndexName="GSI3",
    KeyConditionExpression="entity_type = :et",
    ExpressionAttributeValues={
        ":et": {"S": "festival"},
    },
)
```

### 4.6 특정 월 축제 조회 — FestivalMonthIndex

```python
# 10월 축제 조회
month = 10
resp = ddb.query(
    TableName="TourKoreaDomainData",
    IndexName="FestivalMonthIndex",
    KeyConditionExpression="entity_type = :et AND begins_with(gsi_sk, :prefix)",
    ExpressionAttributeValues={
        ":et": {"S": "festival"},
        ":prefix": {"S": f"FESTIVAL#{month:02d}"},
    },
)
```

### 4.7 도시별 관광지만 조회 — GSI1 + FilterExpression

```python
resp = ddb.query(
    TableName="TourKoreaDomainData",
    IndexName="GSI1",
    KeyConditionExpression="city_key = :ck AND begins_with(domain_sort_key, :prefix)",
    ExpressionAttributeValues={
        ":ck": {"S": "CITY#Sokcho"},
        ":prefix": {"S": "attraction#"},
    },
)
```

### 4.8 페이지네이션 처리

```python
all_items = []
exclusive_start_key = None

while True:
    params = {
        "TableName": "TourKoreaDomainData",
        "KeyConditionExpression": "PK = :pk",
        "ExpressionAttributeValues": {":pk": {"S": "CITY#Gyeongju"}},
    }
    if exclusive_start_key:
        params["ExclusiveStartKey"] = exclusive_start_key

    resp = ddb.query(**params)
    all_items.extend(resp["Items"])

    if "LastEvaluatedKey" in resp:
        exclusive_start_key = resp["LastEvaluatedKey"]
    else:
        break

print(f"경주시 전체: {len(all_items)}건")
```

## 5. 대상 도시 목록 (V1 강원/경북)

### 강원특별자치도 (18개 도시)

| PK | 한글명 |
|----|--------|
| `CITY#Chuncheon` | 춘천시 |
| `CITY#Wonju` | 원주시 |
| `CITY#Gangneung` | 강릉시 |
| `CITY#Donghae` | 동해시 |
| `CITY#Taebaek` | 태백시 |
| `CITY#Sokcho` | 속초시 |
| `CITY#Samcheok` | 삼척시 |
| `CITY#Hongcheon` | 홍천군 |
| `CITY#Hoengseong` | 횡성군 |
| `CITY#Yeongwol` | 영월군 |
| `CITY#Pyeongchang` | 평창군 |
| `CITY#Jeongseon` | 정선군 |
| `CITY#Cheorwon` | 철원군 |
| `CITY#Hwacheon` | 화천군 |
| `CITY#Yanggu` | 양구군 |
| `CITY#Inje` | 인제군 |
| `CITY#Goseong` | 고성군 |
| `CITY#Yangyang` | 양양군 |

### 경상북도 (22개 도시)

| PK | 한글명 |
|----|--------|
| `CITY#Pohang` | 포항시 |
| `CITY#Gyeongju` | 경주시 |
| `CITY#Gimcheon` | 김천시 |
| `CITY#Andong` | 안동시 |
| `CITY#Gumi` | 구미시 |
| `CITY#Yeongju` | 영주시 |
| `CITY#Yeongcheon` | 영천시 |
| `CITY#Sangju` | 상주시 |
| `CITY#Mungyeong` | 문경시 |
| `CITY#Gyeongsan` | 경산시 |
| `CITY#Uiseong` | 의성군 |
| `CITY#Cheongsong` | 청송군 |
| `CITY#Yeongyang` | 영양군 |
| `CITY#Yeongdeok` | 영덕군 |
| `CITY#Cheongdo` | 청도군 |
| `CITY#Goryeong` | 고령군 |
| `CITY#Seongju` | 성주군 |
| `CITY#Chilgok` | 칠곡군 |
| `CITY#Yecheon` | 예천군 |
| `CITY#Bonghwa` | 봉화군 |
| `CITY#Uljin` | 울진군 |
| `CITY#Ulleung` | 울릉군 |

## 6. AWS CLI 예시

```bash
# 안동시 관광지 3건 조회
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --key-condition-expression "PK = :pk AND begins_with(SK, :sk)" \
  --expression-attribute-values '{":pk":{"S":"CITY#Andong"}, ":sk":{"S":"ATTRACTION#"}}' \
  --limit 3 \
  --profile skn26_final \
  --region us-east-1

# 강원도 데이터 수 카운트
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --index-name GSI2 \
  --key-condition-expression "province_key = :pk" \
  --expression-attribute-values '{":pk":{"S":"PROVINCE#강원특별자치도"}}' \
  --select COUNT \
  --profile skn26_final \
  --region us-east-1
```

## 7. 참고사항

- V1 테이블에는 `province_key` 속성이 없는 레코드 4,291건이 있음 (초기 적재 데이터, 모두 강원/경북)
- `quality_status = "passed"` 인 아이템만 벡터 인덱스에 포함됨
- `entity_type = "visitor_statistics"` 아이템은 벡터화 대상에서 제외
- Billing Mode: PAY_PER_REQUEST (온디맨드)
- Point-in-Time Recovery: 활성화
