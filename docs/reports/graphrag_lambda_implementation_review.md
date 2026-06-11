# GraphRAG Lambda 구현 검토 보고서

> 작성일: 2026-06-11
> 대상: S3 Vector `kr-tour-domain-v1`, DynamoDB `TourKoreaDomainData`, GraphRAG retrieval layer
> 결론: GraphRAG 전체 Agent가 아니라 retrieval/graph expansion layer를 Lambda로 구현하는 방향을 권장한다.

## 1. 요약 결론

GraphRAG 기능을 Lambda로 구현하는 것은 **범위를 retrieval layer로 제한할 때 적합**하다.

권장 구조는 다음과 같다.

```text
Backend / Agent
  -> kr-graphrag-retriever Lambda
      1. query embedding 생성
      2. S3 Vector QueryVectors 실행
      3. DynamoDB 정본 재조회
      4. 도시/테마/월/거리 기반 graph expansion
      5. evidence JSON 반환
  -> LLM / Planner Agent
      6. grounded context를 사용해 일정/추천 생성
```

반대로 LLM 호출, 장기 planning, 전체 데이터 재색인, 여러 도시 batch 평가까지 Lambda 하나에 넣는 것은 권장하지 않는다.

## 2. Lambda에 적합한 범위

| 기능 | Lambda 적합도 | 이유 |
| --- | --- | --- |
| query embedding 생성 | 높음 | 짧은 요청 단위, Bedrock API 호출 중심 |
| S3 Vector 검색 | 높음 | stateless API 호출, latency 예측 가능 |
| DynamoDB 정본 재조회 | 높음 | `ddb_pk`/`ddb_sk` 기반 point lookup 또는 city query |
| Graph expansion | 중간~높음 | 같은 도시/테마/월 주변 후보 확장까지는 요청 단위 처리 가능 |
| evidence scoring | 높음 | CPU 계산 중심이며 상태 저장 불필요 |
| grounded context packaging | 높음 | LLM 입력 JSON 생성에 적합 |

Lambda 함수는 검색 후보를 만들고 근거를 정리하는 역할까지만 맡기는 것이 좋다.

## 3. Lambda에 넣지 않는 것이 좋은 범위

| 기능 | 비권장 이유 | 대안 |
| --- | --- | --- |
| 전체 vector 재색인 | 15분 제한, Bedrock 호출량 증가 | Step Functions, ECS/Fargate, Batch |
| 모든 도시 순회 batch 평가 | 실행 시간이 길고 재시도 단위가 큼 | Step Functions Map, 배치 worker |
| LLM 기반 최종 답변 생성 | latency와 비용 추적이 어려워짐 | Backend/Agent layer |
| multi-step itinerary planning | 상태와 중간 결과 관리 필요 | Agent orchestrator |
| 검색 품질 실험/튜닝 | 로그만으로 비교가 어려움 | CLI evaluation, notebook, batch report |

## 4. 현재 시스템과의 역할 분리

현재 배포된 `kr-vector-index` Lambda는 **인덱스 build/upsert 담당**이다. GraphRAG 검색용 Lambda는 별도로 두는 것이 맞다.

| Lambda | 역할 | 실행 시점 |
| --- | --- | --- |
| `kr-vector-index` | DynamoDB 데이터를 embedding 후 S3 Vector에 적재 | 데이터 갱신/재색인 시 |
| `kr-graphrag-retriever` | 사용자 질의로 후보와 graph evidence 검색 | 사용자 요청마다 |

두 역할을 한 Lambda에 합치면 build 권한과 runtime query 권한이 섞인다. 운영에서는 write 권한을 가진 build Lambda와 read/query 중심 retriever Lambda를 분리하는 편이 안전하다.

## 5. 권장 Lambda 입력 계약

```json
{
  "query": "안동에서 전통 분위기 있고 맛집도 있는 1박 2일 코스 추천",
  "city_id": "KR-Andong",
  "themes": ["history", "food"],
  "month": 10,
  "entity_types": ["attraction", "restaurant", "festival"],
  "top_k": 30,
  "expand": {
    "same_city": true,
    "same_theme": true,
    "nearby": true
  }
}
```

필드 의미:

| 필드 | 설명 |
| --- | --- |
| `query` | embedding 대상 사용자 질의 |
| `city_id` | 도시 지정 검색 시 anchor filter |
| `themes` | theme quota 또는 graph expansion 기준 |
| `month` | 방문월/축제 기간 필터 |
| `entity_types` | 검색 대상 유형 제한 |
| `top_k` | S3 Vector 반환 후보 수 |
| `expand` | graph expansion 옵션 |

## 6. 권장 Lambda 출력 계약

```json
{
  "statusCode": 200,
  "retrieval_audit": {
    "vector_bucket": "lovv-vector-dev",
    "vector_index": "kr-tour-domain-v1",
    "embedding_model": "amazon.titan-embed-text-v2:0",
    "top_k": 30
  },
  "candidates": [
    {
      "place_id": "restaurant#123456",
      "entity_type": "restaurant",
      "title": "안동식당",
      "city_id": "KR-Andong",
      "score": 0.82,
      "evidence": {
        "vector_distance": 0.12,
        "theme_matches": ["food"],
        "ddb_pk": "CITY#Andong",
        "ddb_sk": "RESTAURANT#123456"
      }
    }
  ],
  "graph_context": {
    "nodes": [],
    "edges": []
  }
}
```

LLM에는 이 출력 중 `candidates`, `graph_context`, `retrieval_audit`만 전달하고, 원천에 없는 필드는 생성하지 않도록 prompt에서 제한한다.

## 7. 권한 설계

`kr-graphrag-retriever` Lambda role은 write 권한을 갖지 않는 것이 좋다.

필요 권한:

| 서비스 | 권한 |
| --- | --- |
| Bedrock | `bedrock:InvokeModel` for `amazon.titan-embed-text-v2:0` |
| S3 Vectors | `s3vectors:GetVectorBucket`, `s3vectors:GetIndex`, `s3vectors:QueryVectors`, `s3vectors:GetVectors` |
| DynamoDB | `dynamodb:GetItem`, `dynamodb:Query` on `TourKoreaDomainData` and GSIs |
| CloudWatch Logs | 기본 Lambda logging |

불필요하거나 금지할 권한:

| 권한 | 이유 |
| --- | --- |
| `s3vectors:PutVectors` | retriever는 인덱스를 변경하지 않아야 함 |
| `s3vectors:DeleteVectors` | 검색 Lambda에서 삭제 권한 불필요 |
| `dynamodb:DeleteItem` | 검색 경로에서 데이터 삭제 금지 |
| `s3:DeleteObject` | runtime retrieval에는 불필요 |

## 8. 성능과 제한

Lambda로 retrieval layer를 구현할 때 주의할 점:

| 항목 | 검토 |
| --- | --- |
| Timeout | retrieval은 10~30초 안에 끝나야 함. 기본 timeout은 60초부터 시작 권장 |
| Memory | 512MB~1024MB 권장. graph expansion이 커지면 1024MB |
| Top-K | S3 Vector Top-K는 30~100 범위에서 실험 |
| DynamoDB 재조회 | candidate마다 GetItem을 반복하면 느려질 수 있으므로 batch/Query 패턴 검토 |
| Cold start | boto3 client 생성 비용이 있으므로 module-level client cache 고려 |
| 비용 | query마다 Bedrock embedding 1회 + S3 Vector query + DynamoDB read 발생 |

## 9. 실패 처리

Lambda 응답은 실패 원인을 구분해야 한다.

| 실패 | 처리 |
| --- | --- |
| query 누락 | `400`, `query is required` |
| embedding 실패 | `502`, Bedrock error summary |
| vector query 실패 | `502`, S3 Vector error summary |
| DynamoDB 재조회 실패 | 후보에서 제외하고 `failed_rehydration`에 기록 |
| 후보 없음 | `200`, empty candidates + fallback reason |

후보 없음은 시스템 오류가 아니므로 `200`으로 반환하고, Agent가 도시/테마 완화 검색을 재시도할 수 있게 한다.

## 10. 구현 순서

1. `src/kr_graphrag/retrieve.py`
   - Titan V2 query embedding
   - S3 Vector QueryVectors wrapper
2. `src/kr_graphrag/rehydrate.py`
   - `ddb_pk`/`ddb_sk` 기반 DynamoDB 정본 재조회
3. `src/kr_graphrag/graph.py`
   - same city, same theme, active month expansion
4. `src/kr_graphrag/score.py`
   - vector distance + graph evidence score
5. `src/kr_graphrag/handlers/retriever_handler.py`
   - Lambda event validation and response packaging
6. Terraform
   - `kr-graphrag-retriever` Lambda
   - read-only S3 Vector IAM
   - Bedrock invoke and DynamoDB read IAM
7. Evaluation report
   - 샘플 질의 10개
   - city anchored / city discovery / theme quota 결과 비교

## 11. 최종 권고

`kr-graphrag-retriever` Lambda를 별도로 추가하는 방향을 권장한다.

이 Lambda는 S3 Vector와 DynamoDB를 조합해 grounded 후보 JSON을 반환하고, LLM 답변 생성은 Backend/Agent 계층에서 담당한다. 이렇게 나누면 권한 분리, 테스트, 비용 추적, 검색 품질 튜닝이 모두 쉬워진다.
