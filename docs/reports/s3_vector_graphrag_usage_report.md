# S3 Vector 기반 GraphRAG 활용 보고서

> 작성일: 2026-06-11
> 대상 시스템: KR 데이터 파이프라인 `TourKoreaDomainData` + S3 Vector `lovv-vector-dev/kr-tour-domain-v1`
> 목적: 현재 구축된 S3 Vector 적재 라인을 GraphRAG 형태로 서비스 검색/추천 Agent에 활용하는 방안 정의

## 1. 결론

현재 구현된 S3 Vector 인덱스는 GraphRAG의 **semantic retrieval 계층**으로 사용할 수 있다.

다만 S3 Vector 자체는 그래프 데이터베이스가 아니다. 따라서 GraphRAG처럼 활용하려면 다음처럼 역할을 나누는 구조가 맞다.

| 계층 | 저장소 | 역할 |
| --- | --- | --- |
| Vector Retrieval | S3 Vector `kr-tour-domain-v1` | 사용자 질의와 의미적으로 가까운 도시/관광지/음식점/축제 후보 검색 |
| Graph Store / Source of Truth | DynamoDB `TourKoreaDomainData` | 후보의 정본 필드, 도시-장소-테마-축제 관계, 재검증 데이터 조회 |
| Graph Expansion | Application/Lambda/Agent Logic | vector 후보 주변의 같은 도시, 같은 테마, 같은 기간, 인접 장소를 확장 |
| Generation | LLM Agent | 검색 결과와 그래프 근거를 사용해 일정/추천/설명 생성 |

즉, 최종 구조는 **VectorRAG + DynamoDB graph expansion**이다. Neo4j/Neptune 같은 전용 그래프 DB 없이도 현재 DynamoDB 스키마와 S3 Vector metadata를 이용해 1차 GraphRAG를 구현할 수 있다.

## 2. 현재 적재 라인 기준

현재 vector index 적재는 S3 Raw가 아니라 DynamoDB 전처리 결과를 기준으로 한다.

```text
S3 Raw
  -> domain preprocessing
  -> DynamoDB TourKoreaDomainData
  -> GSI3(entity_type) export
  -> rich embedding_text 생성
  -> Bedrock Titan V2 embedding
  -> S3 Vector kr-tour-domain-v1
```

vector 적재 대상 entity type은 다음이다.

| Entity | Vector화 여부 | GraphRAG 역할 |
| --- | --- | --- |
| `city` / `city_metadata` | 포함 | 도시 discovery, 도시 단위 집계의 중심 노드 |
| `attraction` | 포함 | 관광 후보 노드 |
| `restaurant` | 포함 | 식당 후보 노드 |
| `festival` | 포함 | 시기성 이벤트 후보 노드 |
| `visitor_statistics` | 제외 | 혼잡도/방문월 점수 산정 시 DynamoDB에서 재조회 |

현재 vector key는 다음 형식이다.

```text
{entity_type}#{source_id}#{chunk_no}
```

예:

```text
restaurant#123456#0
attraction#987654#0
festival#A001#0
city#Andong#0
```

GraphRAG에서 장소 식별자는 `chunk_no`를 제외한 `{entity_type}#{source_id}`를 `place_id`로 쓰는 것이 적절하다.

## 3. GraphRAG로 볼 때의 노드와 엣지

### 3.1 노드 설계

현재 데이터 기준으로 다음 노드 타입을 만들 수 있다.

| Node Type | ID 예시 | 원천 |
| --- | --- | --- |
| City | `city#KR-Andong` | city/city_metadata item |
| Attraction | `attraction#<content_id>` | attraction item |
| Restaurant | `restaurant#<content_id>` | restaurant item |
| Festival | `festival#<content_id>` | festival item |
| Theme | `theme#history`, `theme#food` | `theme_tags`, `restaurant_category`, `theme` |
| Season/Month | `month#10`, `season#autumn` | `visit_months`, `season_tags`, festival dates |

### 3.2 엣지 설계

DynamoDB item과 vector metadata로 다음 관계를 계산할 수 있다.

| Edge | 의미 | 생성 기준 |
| --- | --- | --- |
| `CITY_HAS_PLACE` | 도시가 장소를 포함 | `city_id`, `PK = CITY#...` |
| `PLACE_HAS_THEME` | 장소가 테마를 가짐 | `theme_tags`, `theme`, `restaurant_category` |
| `PLACE_ACTIVE_IN_MONTH` | 특정 월 방문/운영 적합 | `visit_months`, 축제 기간 |
| `PLACE_NEAR_PLACE` | 지리적으로 가까움 | `latitude`, `longitude` 거리 계산 |
| `CITY_HAS_FESTIVAL` | 도시의 축제 | `entity_type = festival`, `city_id` |
| `PLACE_FROM_SOURCE` | 원천 추적 | `ddb_pk`, `ddb_sk`, `raw_s3_uri` |

초기 구현은 엣지를 별도 저장하지 않고, DynamoDB 조회 결과에서 런타임 계산해도 충분하다. 추천 품질과 latency가 문제가 되면 `GRAPH#...` 형태의 adjacency item을 DynamoDB에 추가하면 된다.

## 4. 추천 실행 흐름

GraphRAG 검색은 다음 5단계로 구성한다.

```text
1. Query Understanding
   - 사용자 질의에서 목적지, 일정, 월, 테마, 동행자, 음식 선호 추출

2. Vector Retrieval
   - Bedrock Titan V2로 query embedding 생성
   - S3 Vector QueryVectors 실행
   - 필터: country, city_id, entity_type, theme_tags, visit_months 등

3. Graph Expansion
   - vector 결과의 ddb_pk/ddb_sk로 DynamoDB 정본 재조회
   - 같은 city_id의 주변 관광지/식당/축제 확장
   - theme/month/거리 기반 엣지로 후보 보강

4. Evidence Scoring
   - vector distance
   - theme coverage
   - city consistency
   - date/festival validity
   - distance/locality
   - source field completeness

5. Grounded Generation
   - 최종 후보와 근거 필드만 LLM에 전달
   - LLM은 없는 정보를 만들지 않고, 부족한 필드는 unknown 또는 확인 필요로 표시
```

## 5. Query 패턴별 활용 방법

### 5.1 도시 미지정 검색

사용자가 “가을에 전통 분위기 있고 맛집도 있는 국내 여행지 추천”처럼 도시를 지정하지 않은 경우:

1. S3 Vector에서 `country = KR` 필터로 Top-K 검색
2. 결과를 `city_id`로 group-by
3. 도시별로 관광지/식당/축제 evidence 수와 theme coverage 계산
4. 상위 도시를 선정
5. 선정 도시별로 DynamoDB에서 관련 장소를 확장

핵심은 vector 결과를 바로 최종 답으로 쓰지 않고, 도시 단위 graph 집계의 seed로 쓰는 것이다.

### 5.2 도시 지정 검색

사용자가 “안동에서 1박 2일 코스 추천”처럼 도시를 지정한 경우:

1. `city_id = KR-Andong` 또는 `PK = CITY#Andong` 기준으로 anchored 검색
2. S3 Vector 검색 결과에 타 도시가 섞이면 폐기
3. DynamoDB에서 같은 도시의 restaurant/festival/attraction을 추가 조회
4. 거리와 테마로 일정 순서를 구성

이 방식은 `anchor_violation`을 줄이고, 도시 경계를 벗어난 추천을 막는다.

### 5.3 테마 quota 검색

사용자가 “역사 + 음식 중심”처럼 복수 테마를 말한 경우:

1. raw query로 전체 Top-K 검색
2. theme별로 `theme_tags` 필터 query를 추가 실행
3. 각 테마에서 최소 후보 수를 확보
4. 중복 place_id는 병합
5. 최종 후보를 점수화

이 방식은 인기 테마 하나가 결과를 독점하는 문제를 줄인다.

## 6. 필요한 코드 구조

현재 repo 기준으로 다음 모듈을 추가하는 것이 좋다.

```text
src/kr_graphrag/
├── query.py        # 사용자 질의 구조화: destination, month, themes, entity_types
├── retrieve.py     # Bedrock query embedding + S3 Vector QueryVectors
├── graph.py        # DynamoDB 재조회와 graph expansion
├── score.py        # vector/graph/evidence 점수화
├── pack.py         # LLM에 넘길 grounded context 생성
└── cli.py          # console 테스트와 batch evaluation
```

초기 버전은 Lambda보다 CLI로 먼저 검증하는 편이 좋다. 검색 품질을 조정해야 하므로, CloudWatch 로그만 보며 튜닝하면 느리다.

## 7. 필수 API 계약

GraphRAG retrieval 함수는 아래 형태를 권장한다.

```python
def retrieve_candidates(
    query: str,
    *,
    city_id: str | None = None,
    themes: list[str] | None = None,
    month: int | None = None,
    entity_types: list[str] | None = None,
    top_k: int = 30,
) -> GraphRagResult:
    ...
```

반환 구조:

```json
{
  "query": "...",
  "retrieval": {
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
        "themes": ["food", "local"],
        "ddb_pk": "CITY#Andong",
        "ddb_sk": "RESTAURANT#123456"
      }
    }
  ],
  "graph_context": {
    "cities": [],
    "themes": [],
    "edges": []
  }
}
```

## 8. 현재 구현에서 바로 가능한 확인 명령

### 8.1 적재 현황 확인

```powershell
aws s3vectors list-vectors `
  --vector-bucket-name lovv-vector-dev `
  --index-name kr-tour-domain-v1 `
  --max-results 10 `
  --return-metadata `
  --profile skn26_final `
  --region us-east-1
```

### 8.2 manifest 확인

```powershell
aws s3 cp `
  s3://lovv-data-pipeline-dev-925273580929/processed/KR/vector/manifests/latest.json `
  - `
  --profile skn26_final `
  --region us-east-1
```

### 8.3 Lambda로 도시 단위 적재

```powershell
aws lambda invoke `
  --function-name kr-vector-index `
  --cli-binary-format raw-in-base64-out `
  --payload '{"command":"build","dry_run":false,"city_pk":"CITY#Andong"}' `
  response-andong.json `
  --profile skn26_final `
  --region us-east-1
```

## 9. 구현 우선순위

### Phase 1: Retrieval 확인

- query text를 Titan V2로 embedding
- S3 Vector QueryVectors 호출
- metadata에서 `place_id`, `entity_type`, `city_id`, `ddb_pk`, `ddb_sk` 추출
- DynamoDB `GetItem` 또는 `Query`로 정본 재조회

완료 기준:

- 도시 지정 질의에서 타 도시 결과가 섞이지 않는다.
- `ddb_pk`/`ddb_sk`로 재조회가 성공한다.
- LLM에 전달할 근거 JSON이 생성된다.

### Phase 2: Graph Expansion

- 같은 `city_id`의 attraction/restaurant/festival 확장
- `theme_tags` 기반 theme coverage 계산
- `latitude`/`longitude` 기반 근거리 후보 계산
- 축제 기간과 여행월 매칭

완료 기준:

- vector 후보가 부족해도 같은 도시/테마 후보로 보강된다.
- 결과마다 어떤 graph edge로 확장됐는지 설명 가능하다.

### Phase 3: Scoring

- vector distance normalized score
- theme match score
- city consistency score
- date/festival validity score
- distance score
- source completeness score

완료 기준:

- 추천 결과에 score breakdown이 포함된다.
- LLM 답변 전 후보 정렬이 deterministic하다.

### Phase 4: Agent 연결

- Candidate Evidence Agent 또는 Planner Agent에서 `retrieve_candidates()` 호출
- LLM prompt에는 후보 JSON과 score/evidence만 전달
- 생성 결과에는 근거 place_id와 source를 포함

완료 기준:

- “왜 이 장소를 추천했는지”를 metadata와 DynamoDB 필드로 설명할 수 있다.
- 없는 주소/메뉴/기간을 LLM이 만들어내지 않는다.

## 10. 리스크와 대응

| 리스크 | 설명 | 대응 |
| --- | --- | --- |
| Lambda 15분 제한 | 전체 3,000+ vector 적재/재색인은 Lambda 단일 실행에 부적합 | city_pk 단위 실행 또는 Step Functions 분할 |
| S3 Vector는 그래프 DB가 아님 | 관계 탐색 기능이 없음 | DynamoDB graph expansion 레이어 추가 |
| metadata 2KB 제한 | filterable metadata를 많이 넣으면 실패 | 검색 필터용 key만 metadata에 두고 상세 필드는 DynamoDB 재조회 |
| theme 품질 편차 | 원천 데이터의 테마 필드가 부족할 수 있음 | chunk 생성 시 파생 태그 보강, 품질 리포트 추가 |
| hallucination | LLM이 검색되지 않은 정보를 생성할 수 있음 | grounded context만 전달하고 source/evidence 필수화 |

## 11. 권장 최종 아키텍처

```text
User Query
  -> Query Parser
  -> Titan V2 Query Embedding
  -> S3 Vector QueryVectors
  -> Candidate Vector Results
  -> DynamoDB Source Rehydration
  -> Graph Expansion
       - same city
       - same theme
       - active month
       - nearby places
  -> Evidence Scoring
  -> Grounded Context Pack
  -> LLM Response / Itinerary Agent
```

이 구조에서는 S3 Vector가 “찾는 역할”을 맡고, DynamoDB가 “검증하고 연결하는 역할”을 맡는다. 이것이 현재 Lovv 데이터 구조에서 가장 현실적인 GraphRAG 적용 방식이다.

## 12. 다음 작업 제안

1. `src/kr_graphrag/retrieve.py`를 만들어 query embedding + S3 Vector query를 구현한다.
2. `src/kr_graphrag/graph.py`에서 `ddb_pk`/`ddb_sk` 재조회와 같은 도시 확장을 구현한다.
3. `src/kr_graphrag/score.py`에서 vector distance와 graph evidence를 합산한다.
4. `docs/reports/graphrag_evaluation_report.md`에 샘플 질의 10개 결과를 기록한다.
