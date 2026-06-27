# AgentCore v1 - S3 Vector Index 사용 가이드

> 버킷: `lovv-agentcore-v1-vector`
> 인덱스: `kr-agentcore-v1`
> 리전: `us-east-1`
> 대상: 강원특별자치도 + 경상북도 (2,125 벡터)

## 1. 인프라 정보

| 항목 | 값 |
|------|-----|
| S3 Vector Bucket | `lovv-agentcore-v1-vector` |
| Vector Index | `kr-agentcore-v1` |
| Bucket ARN | `arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-agentcore-v1-vector` |
| Index ARN | `arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-agentcore-v1-vector/index/kr-agentcore-v1` |
| Dimension | 1024 |
| Distance Metric | cosine |
| Data Type | float32 |
| Embedding Model | `amazon.titan-embed-text-v2:0` |

## 2. 벡터 구조

### 2.1 Vector Key 형식

```
{entity_type}#{source_id}#0
```

예시:
- `attraction#ATT-126023#0`
- `festival#FEST-2948110#0`
- `city#CITY-KR-42-001#0`

### 2.2 Metadata 필드

| 필드 | 타입 | 필터 가능 | 설명 |
|------|------|-----------|------|
| `country` | string | ✅ | 항상 `"KR"` |
| `province` | string | ✅ | `"강원특별자치도"` 또는 `"경상북도"` |
| `city_id` | string | ✅ | 도시 ID (예: `KR-42-001`) |
| `city_name_en` | string | ✅ | 영문 도시명 |
| `city_name_ko` | string | ✅ | 한글 도시명 |
| `entity_type` | string | ✅ | `city`, `attraction`, `festival` |
| `source_type` | string | ✅ | = entity_type |
| `source_id` | string | ✅ | 원본 엔티티 ID |
| `place_id` | string | ✅ | `{entity_type}#{source_id}` |
| `title` | string | ✅ | 장소/축제 이름 |
| `class_tags` | list | ✅ | 분류 태그 |
| `theme_tags` | list | ✅ | 테마 태그 |
| `season_tags` | list | ✅ | 시즌 태그 |
| `visit_months` | list | ✅ | 방문 추천 월 |
| `latitude` | number | ✅ | 위도 |
| `longitude` | number | ✅ | 경도 |
| `indoor_outdoor` | string | ✅ | 실내/실외 (enrichment) |
| `vibe_tags` | list | ✅ | 분위기 태그 (enrichment) |
| `experience_tags` | list | ✅ | 경험 태그 (enrichment) |
| `companion_fit` | list | ✅ | 동행 적합성 (enrichment) |
| `raw_s3_uri` | string | ❌ | S3 원본 경로 |
| `ddb_pk` | string | ❌ | DynamoDB PK |
| `ddb_sk` | string | ❌ | DynamoDB SK |
| `embedding_model` | string | ❌ | 임베딩 모델명 |

### 2.3 Embedding Text 구성

벡터 임베딩은 아래 형식의 한국어 텍스트로 생성됩니다:

```
이름: 하회마을
유형: 관광지
도시: 안동시 (Andong)
지역: 경상북도
주소: 경상북도 안동시 풍천면
분류: 역사, 전통
테마: history
설명: 유네스코 세계유산으로 등재된 전통 마을...
```

## 3. Query 사용법

### 3.1 Python SDK (boto3)

```python
import json
import boto3

session = boto3.Session(profile_name="skn26_final", region_name="us-east-1")
bedrock = session.client("bedrock-runtime")
s3vectors = session.client("s3vectors")

# 1. 검색 텍스트를 임베딩으로 변환
query_text = "강릉에서 바다를 볼 수 있는 관광지"
embed_resp = bedrock.invoke_model(
    modelId="amazon.titan-embed-text-v2:0",
    body=json.dumps({
        "inputText": query_text,
        "dimensions": 1024,
        "normalize": True,
    }).encode("utf-8"),
)
embedding = json.loads(embed_resp["body"].read())["embedding"]

# 2. 벡터 유사도 검색
results = s3vectors.query_vectors(
    vectorBucketName="lovv-agentcore-v1-vector",
    indexName="kr-agentcore-v1",
    queryVector={"float32": embedding},
    topK=10,
    returnDistance=True,
    returnMetadata=True,
)

# 3. 결과 출력
for vector in results.get("vectors", []):
    meta = vector.get("metadata", {})
    print(f"  {meta.get('title')} ({meta.get('city_name_ko')}) - distance: {vector.get('distance', 'N/A')}")
```

### 3.2 메타데이터 필터를 사용한 검색

```python
# 강원도 관광지만 검색
results = s3vectors.query_vectors(
    vectorBucketName="lovv-agentcore-v1-vector",
    indexName="kr-agentcore-v1",
    queryVector={"float32": embedding},
    topK=5,
    returnDistance=True,
    returnMetadata=True,
    filter={
        "andAll": [
            {"equals": {"key": "province", "value": "강원특별자치도"}},
            {"equals": {"key": "entity_type", "value": "attraction"}},
        ]
    },
)
```

### 3.3 특정 도시 축제 검색

```python
# 안동시 축제 검색
results = s3vectors.query_vectors(
    vectorBucketName="lovv-agentcore-v1-vector",
    indexName="kr-agentcore-v1",
    queryVector={"float32": embedding},
    topK=5,
    returnDistance=True,
    returnMetadata=True,
    filter={
        "andAll": [
            {"equals": {"key": "city_name_en", "value": "Andong"}},
            {"equals": {"key": "entity_type", "value": "festival"}},
        ]
    },
)
```

### 3.4 복합 필터 (지역 + 테마)

```python
# 경상북도에서 역사 관련 장소
results = s3vectors.query_vectors(
    vectorBucketName="lovv-agentcore-v1-vector",
    indexName="kr-agentcore-v1",
    queryVector={"float32": embedding},
    topK=10,
    returnDistance=True,
    returnMetadata=True,
    filter={
        "andAll": [
            {"equals": {"key": "province", "value": "경상북도"}},
            {"equals": {"key": "entity_type", "value": "attraction"}},
        ]
    },
)
```

## 4. AWS CLI 사용법

### 4.1 벡터 검색

```bash
# query-vector.json 파일 생성 (임베딩 벡터)
# {"float32": [0.1, 0.2, ...]}  (1024 차원)

aws s3vectors query-vectors \
  --vector-bucket-name lovv-agentcore-v1-vector \
  --index-name kr-agentcore-v1 \
  --top-k 5 \
  --query-vector file://query-vector.json \
  --return-distance \
  --return-metadata \
  --profile skn26_final \
  --region us-east-1
```

### 4.2 특정 벡터 조회

```bash
aws s3vectors get-vectors \
  --vector-bucket-name lovv-agentcore-v1-vector \
  --index-name kr-agentcore-v1 \
  --keys '["attraction#ATT-126023#0"]' \
  --return-metadata \
  --profile skn26_final \
  --region us-east-1
```

### 4.3 벡터 추가/업데이트

```bash
# vectors.json: [{key, data: {float32: [...]}, metadata: {...}}, ...]
aws s3vectors put-vectors \
  --vector-bucket-name lovv-agentcore-v1-vector \
  --index-name kr-agentcore-v1 \
  --vectors file://vectors.json \
  --profile skn26_final \
  --region us-east-1
```

### 4.4 인덱스 정보 확인

```bash
aws s3vectors get-index \
  --vector-bucket-name lovv-agentcore-v1-vector \
  --index-name kr-agentcore-v1 \
  --profile skn26_final \
  --region us-east-1
```

## 5. 벡터 통계

| 항목 | 값 |
|------|-----|
| 총 벡터 수 | 2,125 |
| attraction | 1,942 |
| city_metadata | 78 |
| festival | 105 |
| 임베딩 실패 | 0 |
| 적재일 | 2026-06-27 |

## 6. IAM 권한

### Reader (조회 전용)

AgentCore v1에서 검색만 수행할 때:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3vectors:GetVectorBucket",
    "s3vectors:GetIndex",
    "s3vectors:QueryVectors"
  ],
  "Resource": [
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-agentcore-v1-vector",
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-agentcore-v1-vector/index/kr-agentcore-v1"
  ]
}
```

### Writer (적재/업데이트)

벡터 빌드 파이프라인:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3vectors:GetVectorBucket",
    "s3vectors:GetIndex",
    "s3vectors:ListVectors",
    "s3vectors:GetVectors",
    "s3vectors:QueryVectors",
    "s3vectors:PutVectors"
  ],
  "Resource": [
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-agentcore-v1-vector",
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-agentcore-v1-vector/index/kr-agentcore-v1"
  ]
}
```

### Bedrock 임베딩 모델 권한

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
}
```

## 7. 벡터 재빌드

V1 테이블 데이터가 변경된 경우, 벡터 인덱스를 재빌드합니다:

```bash
cd d:\bootcamp\workspace\project\03_final\02_lovv_data_collect

# Dry-run (적재 없이 확인만)
python scripts/build_agentcore_v1_vectors.py --profile skn26_final --dry-run

# 전체 재빌드
python scripts/build_agentcore_v1_vectors.py --profile skn26_final

# 특정 도시만 재빌드
python scripts/build_agentcore_v1_vectors.py --profile skn26_final --city-pk "CITY#Andong"
```

## 8. DynamoDB → Vector 연동 흐름

```
TourKoreaDomainData (V1)
    │
    ├─ GSI3 (entity_type) → export: city_metadata, attraction, festival
    │
    ├─ Filter: province = 강원특별자치도 or 경상북도
    │
    ├─ build_chunks() → VectorChunk (key, embedding_text, metadata)
    │
    ├─ embed_chunks() → Amazon Titan Embed Text v2 (1024d, cosine)
    │
    └─ put_vectors_sdk() → lovv-agentcore-v1-vector / kr-agentcore-v1
```

## 9. 주의사항

- cosine 유사도 사용: distance가 낮을수록 유사함 (0 = 동일)
- 필터 적용 시 topK는 필터링 전 후보 수가 아닌 최종 반환 수
- metadata filterable 크기 제한: 2048 bytes
- 벡터 key는 중복 시 덮어쓰기됨 (upsert 동작)
- `quality_status = "passed"` 아이템만 벡터에 포함됨
