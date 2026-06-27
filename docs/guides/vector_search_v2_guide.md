# S3 Vectors 검색 사용 가이드 (V2 기준)

## 인덱스 개요

| 항목 | 값 |
|---|---|
| S3 Vectors 버킷 | `lovv-vector-dev` |
| 인덱스 이름 | `kr-tour-domain-v1` |
| 벡터 수 | **7,073** |
| 임베딩 모델 | Amazon Titan Embed Text v2 |
| 벡터 차원 | 1024 |
| Distance Metric | Cosine |
| 소스 테이블 | `TourKoreaDomainDataV2` |

## 벡터화 대상

| entity_type | 벡터화 | 이유 |
|---|---|---|
| attraction | ✅ | 관광지 검색 |
| festival | ✅ | 축제 검색 |
| city / city_metadata | ✅ | 도시 정보 검색 |
| visitor_statistics | ❌ | 수치 데이터 (벡터 검색 부적합) |
| restaurant | ❌ | 제외 결정 |

## 벡터 검색 코드 (Python)

### 기본 검색

```python
import boto3
import json

bedrock = boto3.client("bedrock-runtime")
s3vectors = boto3.client("s3vectors")

# 1. 쿼리 텍스트 임베딩
query = "강릉에서 바다가 보이는 관광지"
resp = bedrock.invoke_model(
    modelId="amazon.titan-embed-text-v2:0",
    body=json.dumps({"inputText": query, "dimensions": 1024, "normalize": True}),
)
embedding = json.loads(resp["body"].read())["embedding"]

# 2. 벡터 검색
result = s3vectors.query_vectors(
    vectorBucketName="lovv-vector-dev",
    indexName="kr-tour-domain-v1",
    queryVector={"float32": embedding},
    topK=10,
    returnMetadata=True,
)

# 3. 결과 출력
for v in result["vectors"]:
    meta = v.get("metadata", {})
    print(f"{meta.get('city_name_ko')} | {meta.get('entity_type')} | {meta.get('title')}")
```

### 검색 결과 예시

```
Query: "강릉에서 바다가 보이는 관광지"
Results:
  강릉시 | attraction | 순포해변
  강릉시 | attraction | 안목해변
  강릉시 | attraction | 강문해변
  강릉시 | attraction | 임해자연휴양림
  강릉시 | attraction | 등명해변(등명해수욕장)
```

## 검색 시나리오

### 테마 검색

```python
query = "겨울에 눈꽃을 볼 수 있는 축제"
# → 평창 눈꽃축제, 태백산 눈축제 등
```

### 지역 + 활동 검색

```python
query = "경주에서 역사 유적지를 방문하고 싶어"
# → 불국사, 석굴암, 첨성대, 대릉원 등
```

### 자연 검색

```python
query = "울릉도 해안 절경"
# → 봉래폭포, 도동약수공원, 태하해안산책로 등
```

## 메타데이터 필드

벡터에 저장된 메타데이터:

| 필드 | 타입 | 설명 |
|---|---|---|
| city_name_ko | string | 한글 도시명 |
| city_name_en | string | 영문 도시명 |
| entity_type | string | attraction / festival / city |
| title | string | 관광지/축제 제목 |
| description | string | 설명 (임베딩 텍스트 원본) |
| theme_tags | list | 테마 태그 |
| season_tags | list | 계절 태그 |
| visit_months | list | 방문 추천 월 |
| latitude | float | 위도 |
| longitude | float | 경도 |
| content_id | string | TourAPI content ID |

## 벡터 빌드 방법

### Lambda 호출

```bash
# payload 생성
echo '{"command":"vector-build","table_name":"TourKoreaDomainDataV2","rebuild_mode":"full"}' > payload.json

# Lambda invoke (15분 이내 완료 가능한 규모일 때)
aws lambda invoke \
  --function-name kr-pipeline-loader \
  --cli-read-timeout 900 \
  --payload fileb://payload.json \
  response.json
```

### 로컬 실행 (대규모 / 타임아웃 우회)

```python
import boto3, sys
sys.path.insert(0, 'src')
from kr_vector_index.export import export_items
from kr_vector_index.chunks import build_chunks
from kr_vector_index.embed import embed_chunks
from kr_vector_index.upsert import build_vector_records, put_vectors_sdk

ddb = boto3.client('dynamodb')
bedrock = boto3.client('bedrock-runtime')
s3vectors = boto3.client('s3vectors')

items = export_items(ddb, table_name='TourKoreaDomainDataV2', index_name='EntityTypeDomainIndex')
chunks = build_chunks(items)
embeddings = embed_chunks(bedrock, chunks)
records = build_vector_records(chunks, embeddings)

# Dedup before upsert
seen = set()
unique = [r for r in records if r['key'] not in seen and not seen.add(r['key'])]
put_vectors_sdk(s3vectors, unique, vector_bucket='lovv-vector-dev', index_name='kr-tour-domain-v1')
```

## IAM 권한

### 검색 (읽기 전용)

```json
{
  "Effect": "Allow",
  "Action": ["s3vectors:QueryVectors", "s3vectors:GetVectorBucket", "s3vectors:GetIndex"],
  "Resource": [
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-vector-dev",
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-vector-dev/index/kr-tour-domain-v1"
  ]
}
```

### 임베딩 (Bedrock)

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
}
```

## 주의사항

1. **queryVector 형식**: `{"float32": [...]}`로 dict 형태로 전달
2. **returnMetadata**: `True`를 명시해야 메타데이터 반환됨
3. **중복 키 방지**: upsert 시 `put_vectors`에 동일 키가 있으면 에러 (dedup 필요)
4. **벡터 빌드 시간**: 9,000개 기준 약 44분 (Bedrock 임베딩이 병목)
5. **비용**: Bedrock Titan Embed v2 호출당 ~$0.00003 (9,000개 ≈ $0.27)
6. **타임아웃**: Lambda 15분 제한 시 9,000+개는 로컬 실행 권장
