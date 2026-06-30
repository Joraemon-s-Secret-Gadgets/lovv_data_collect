# DynamoDB V2 and S3 Vector V2 Usage Guide

## 1. Purpose

This guide explains how to use the current KR domain data stack:

- DynamoDB source table: `TourKoreaDomainDataV2`
- S3 Vector bucket/index: `lovv-vector-dev` / `kr-tour-domain-v2`
- Embedding model: `amazon.titan-embed-text-v2:0`

The recommended runtime pattern is:

1. Use S3 Vector for semantic candidate search.
2. Read `ddb_pk` and `ddb_sk` from vector metadata.
3. Use DynamoDB `GetItem` or `Query` to hydrate the full domain record.

This keeps vector metadata compact while preserving DynamoDB as the source of truth.

## 2. Current Live State

Last verified: 2026-06-30 KST.

| Resource | Value |
| --- | --- |
| AWS account | `925273580929` |
| Region | `us-east-1` |
| DynamoDB table | `TourKoreaDomainDataV2` |
| DynamoDB status | `ACTIVE` |
| DynamoDB billing | `PAY_PER_REQUEST` |
| DynamoDB item count | 8,010 |
| S3 Vector bucket | `lovv-vector-dev` |
| S3 Vector index | `kr-tour-domain-v2` |
| S3 Vector count | 7,606 |
| Vector source ingest date | `20260629` |
| Vector manifest | `s3://lovv-data-pipeline-dev-925273580929/processed/KR/details/vector/manifests/latest.json` |

### DynamoDB Entity Counts

| `entity_type` | Count | Vectorized |
| --- | ---: | --- |
| `city_metadata` | 240 | yes |
| `attraction` | 7,024 | yes |
| `festival` | 398 | yes |
| `visitor_statistics` | 348 | no |
| Total | 8,010 |  |

### Vector Counts

| Metric | Count |
| --- | ---: |
| DynamoDB export items | 7,662 |
| Chunks created | 7,662 |
| Duplicate vector keys | 56 |
| Unique vector keys | 7,606 |
| `list-vectors` count | 7,606 |
| Failed vectors | 0 |

The vector count is lower than the export item count because S3 Vectors stores one vector per unique key. Current vector keys are derived from normalized entity type and source id, for example `attraction#971032#0`.

## 3. DynamoDB Data Model

### Primary Key

| Key | Type | Pattern | Example |
| --- | --- | --- | --- |
| `PK` | String | `CITY#{CITY_NAME_EN}` | `CITY#GYEONGJU` |
| `SK` | String | entity-specific | `ATTRACTION#971032` |

### Entity SK Patterns

| `entity_type` | `SK` pattern | Description |
| --- | --- | --- |
| `city_metadata` | `METADATA#city` | City metadata and Wikipedia enrichment |
| `attraction` | `ATTRACTION#{content_id}` | TourAPI attraction |
| `festival` | `FESTIVAL#{content_id}` | TourAPI festival |
| `visitor_statistics` | `STAT#{YYYYMM}` | Monthly visitor statistics |

### GSIs

| GSI | Hash key | Range key | Main use |
| --- | --- | --- | --- |
| `CityDomainIndex` | `city_key` | `domain_sort_key` | City-scoped domain list |
| `ProvinceDomainIndex` | `province_key` | `domain_sort_key` | Province-scoped domain list |
| `EntityTypeDomainIndex` | `entity_type` | `domain_sort_key` | Entity type export/query |
| `FestivalMonthIndex` | `entity_type` | `gsi_sk` | Month-based festival query |

`visitor_statistics` is not included in `FestivalMonthIndex` because it does not use `gsi_sk`.

## 4. DynamoDB Query Examples

Use `region_name="us-east-1"` unless your environment already sets it.

### Query All Items for a City

```python
import boto3
from boto3.dynamodb.conditions import Key

table = boto3.resource("dynamodb", region_name="us-east-1").Table("TourKoreaDomainDataV2")

items = []
params = {
    "KeyConditionExpression": Key("PK").eq("CITY#GYEONGJU"),
}

while True:
    response = table.query(**params)
    items.extend(response.get("Items", []))
    if "LastEvaluatedKey" not in response:
        break
    params["ExclusiveStartKey"] = response["LastEvaluatedKey"]

print(len(items))
```

### Query Attractions for a City

```python
response = table.query(
    KeyConditionExpression=Key("PK").eq("CITY#GYEONGJU")
    & Key("SK").begins_with("ATTRACTION#")
)
attractions = response["Items"]
```

For production code, repeat with `LastEvaluatedKey` as shown in the all-items example.

### Query Festivals by Month

```python
response = table.query(
    IndexName="FestivalMonthIndex",
    KeyConditionExpression=Key("entity_type").eq("festival")
    & Key("gsi_sk").begins_with("FESTIVAL#07")
)
july_festivals = response["Items"]
```

### Query All Items by Entity Type

```python
response = table.query(
    IndexName="EntityTypeDomainIndex",
    KeyConditionExpression=Key("entity_type").eq("attraction"),
)
```

Entity-type queries can return thousands of records. Always paginate with `LastEvaluatedKey`.

### Get a Single Item

```python
response = table.get_item(
    Key={
        "PK": "CITY#GYEONGJU",
        "SK": "ATTRACTION#971032",
    }
)
item = response.get("Item")
```

## 5. DynamoDB CLI Examples

PowerShell can make JSON quoting noisy. Prefer Python for application code. These CLI examples are useful for quick checks.

```bash
aws dynamodb describe-table \
  --table-name TourKoreaDomainDataV2 \
  --region us-east-1
```

```bash
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk":{"S":"CITY#GYEONGJU"}}' \
  --select COUNT \
  --region us-east-1
```

```bash
aws dynamodb query \
  --table-name TourKoreaDomainDataV2 \
  --index-name EntityTypeDomainIndex \
  --key-condition-expression "entity_type = :et" \
  --expression-attribute-values '{":et":{"S":"attraction"}}' \
  --select COUNT \
  --region us-east-1
```

## 6. S3 Vector Metadata Contract

Vector records are compact search documents. They are not the full source of truth.

Common metadata fields:

| Field | Meaning |
| --- | --- |
| `country` | Country code, currently `KR` |
| `entity_type` | `city`, `attraction`, or `festival` |
| `source_type` | Same role as `entity_type` for retrieval |
| `source_id` | Source id used in vector key |
| `place_id` | Stable place id, e.g. `attraction#971032` |
| `city_id` | KR city id |
| `city_name_en` | English city key |
| `city_name_ko` | Korean city name |
| `province` | Province name |
| `title` | Attraction/festival title when applicable |
| `theme_tags` | Compact theme/classification tags |
| `latitude` / `longitude` | Location when available |
| `raw_s3_uri` | Raw detail source path |
| `ddb_pk` | DynamoDB `PK` for hydration |
| `ddb_sk` | DynamoDB `SK` for hydration |
| `embedding_model` | `amazon.titan-embed-text-v2:0` |

Use `ddb_pk` and `ddb_sk` to fetch the complete DynamoDB item after vector search.

## 7. Vector Search Example

This example embeds a Korean natural-language query, searches S3 Vector V2, and hydrates the top results from DynamoDB.

```python
import json
import boto3

REGION = "us-east-1"
TABLE_NAME = "TourKoreaDomainDataV2"
VECTOR_BUCKET = "lovv-vector-dev"
INDEX_NAME = "kr-tour-domain-v2"
MODEL_ID = "amazon.titan-embed-text-v2:0"

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
s3vectors = boto3.client("s3vectors", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


def embed_query(text: str) -> list[float]:
    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True,
        }).encode("utf-8"),
    )
    body = json.loads(response["body"].read())
    return [float(value) for value in body["embedding"]]


def search(text: str, top_k: int = 5) -> list[dict]:
    embedding = embed_query(text)
    result = s3vectors.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        queryVector={"float32": embedding},
        topK=top_k,
        returnMetadata=True,
        returnDistance=True,
    )

    hydrated = []
    for vector in result.get("vectors", []):
        metadata = vector.get("metadata", {})
        pk = metadata.get("ddb_pk")
        sk = metadata.get("ddb_sk")
        item = None
        if pk and sk:
            item = table.get_item(Key={"PK": pk, "SK": sk}).get("Item")
        hydrated.append({
            "vector_key": vector.get("key"),
            "distance": vector.get("distance"),
            "metadata": metadata,
            "item": item,
        })
    return hydrated


for row in search("경주 문화유산 사찰 역사 관광지", top_k=5):
    item = row["item"] or {}
    print(row["distance"], row["vector_key"], item.get("title"), item.get("PK"), item.get("SK"))
```

## 8. Vector CLI Checks

List indexes:

```bash
aws s3vectors list-indexes \
  --vector-bucket-name lovv-vector-dev \
  --region us-east-1
```

Check that V2 is not empty:

```bash
aws s3vectors list-vectors \
  --vector-bucket-name lovv-vector-dev \
  --index-name kr-tour-domain-v2 \
  --max-results 5 \
  --region us-east-1
```

For an exact count, use SDK pagination rather than a single CLI page.

```python
import boto3

s3vectors = boto3.client("s3vectors", region_name="us-east-1")
params = {
    "vectorBucketName": "lovv-vector-dev",
    "indexName": "kr-tour-domain-v2",
    "maxResults": 500,
}

count = 0
while True:
    response = s3vectors.list_vectors(**params)
    count += len(response.get("vectors", []))
    token = response.get("nextToken") or response.get("NextToken")
    if not token:
        break
    params["nextToken"] = token

print(count)
```

Expected current count: `7606`.

## 9. Manifest Check

The latest V2 manifest is stored in S3:

```text
s3://lovv-data-pipeline-dev-925273580929/processed/KR/details/vector/manifests/latest.json
```

Expected key values:

| Field | Expected current value |
| --- | ---: |
| `index_name` | `kr-tour-domain-v2` |
| `table_name` | `TourKoreaDomainDataV2` |
| `source_ingest_date` | `20260629` |
| `items_exported` | 7,662 |
| `chunks_created` | 7,662 |
| `unique_vector_key_count` | 7,606 |
| `duplicate_chunk_key_count` | 56 |
| `vector_success_count` | 7,606 |
| `failed_count` | 0 |
| `list_vectors_verified_count` | 7,606 |

Read the manifest:

```bash
aws s3api get-object \
  --bucket lovv-data-pipeline-dev-925273580929 \
  --key processed/KR/details/vector/manifests/latest.json \
  --region us-east-1 \
  -
```

## 10. Loader Lambda Status

`kr-pipeline-loader` is configured for V2 by default:

| Setting | Value |
| --- | --- |
| Function | `kr-pipeline-loader` |
| Handler | `kr_unified_pipeline.handlers.pipeline_handler.handler` |
| Timeout | 900 seconds |
| Memory | 512 MB |
| `DYNAMODB_TABLE` | `TourKoreaDomainDataV2` |
| `VECTOR_BUCKET` | `lovv-vector-dev` |
| `VECTOR_INDEX` | `kr-tour-domain-v2` |
| `PIPELINE_BUCKET` | `lovv-data-pipeline-dev-925273580929` |

The direct `vector-build` Lambda path is not reliable for the full nationwide rebuild yet. The current implementation embeds all chunks sequentially and timed out at 900 seconds during the 2026-06-30 V2 run.

Do not rely on this payload for a full rebuild until the Lambda implementation is changed to batch/parallelize embedding or is moved behind Step Functions:

```json
{
  "command": "vector-build",
  "table_name": "TourKoreaDomainDataV2",
  "vector_bucket": "lovv-vector-dev",
  "index_name": "kr-tour-domain-v2",
  "rebuild_mode": "full"
}
```

For small smoke tests this command path can still be useful, but production rebuilds should use a bounded batch runner or an orchestrated Step Functions design.

## 11. IAM Actions

Read-only DynamoDB usage:

```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:GetItem",
    "dynamodb:Query",
    "dynamodb:DescribeTable"
  ],
  "Resource": [
    "arn:aws:dynamodb:us-east-1:925273580929:table/TourKoreaDomainDataV2",
    "arn:aws:dynamodb:us-east-1:925273580929:table/TourKoreaDomainDataV2/index/*"
  ]
}
```

Vector search and manifest read:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3vectors:GetVectorBucket",
    "s3vectors:GetIndex",
    "s3vectors:ListIndexes",
    "s3vectors:ListVectors",
    "s3vectors:QueryVectors",
    "s3:GetObject"
  ],
  "Resource": [
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-vector-dev",
    "arn:aws:s3vectors:us-east-1:925273580929:bucket/lovv-vector-dev/index/kr-tour-domain-v2",
    "arn:aws:s3:::lovv-data-pipeline-dev-925273580929/processed/KR/details/vector/manifests/*"
  ]
}
```

Query embedding:

```json
{
  "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
}
```

## 12. Operational Rules

1. Treat DynamoDB as the source of truth.
2. Treat S3 Vector as a retrieval index.
3. Always hydrate search results using `ddb_pk` and `ddb_sk`.
4. Always paginate DynamoDB GSI queries and S3 Vector list calls.
5. Do not include `visitor_statistics` in vector rebuilds.
6. Expect vector count to equal unique vector key count, not raw export count.
7. Check `processed/KR/details/vector/manifests/latest.json` before reporting vector rebuild completion.
8. Do not use old V1 paths such as `kr-tour-domain-v1` or `processed/KR/vector/manifests/latest.json` for the V2 state.
