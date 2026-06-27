# KR 관광지 테마 기반 도시 추천 개인화 검토

> 작성일: 2026-06-25  
> 대상: `data/kr/details`, `TourKoreaDomainData`, `lovv-vector-dev/kr-tour-domain-v1`  
> 목적: 한국 관광지 전처리 데이터를 도시 추천의 근거로 사용하고, 이전 추천 관광지의 테마를 개인화 가중치로 활용할 수 있는지 검토

## 1. 결론

가능하다. 현재 `data/kr/details`는 관광지 단위 전처리와 도시 단위 묶음 추천의 근거 데이터로 사용하기에 충분한 커버리지를 갖고 있다.

다만 개인화 가중치는 S3 Vector 인덱스 내부에 넣는 방식이 아니라, `QueryVectors` 결과와 DynamoDB 정본 재조회 결과를 애플리케이션 또는 GraphRAG retrieval layer에서 재점수화하는 방식이 맞다. 사용자별 가중치는 동적으로 변하므로 벡터 metadata에 저장하지 않고, 요청 시 `theme_weights` 형태로 주입하거나 Backend 사용자 프로필에서 조회해야 한다.

## 2. 현재 데이터와 코드 근거

### 2.1 로컬 전처리 드라이런 결과

`data/kr/details` 211개 파일을 `preprocess_city_payload()` 기준으로 전처리 드라이런한 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| 도시 JSON 파일 | 211 |
| 관광지 item | 6,335 |
| 축제 item | 328 |
| 도시 메타데이터 item | 211 |
| DynamoDB 적재 대상 item | 6,874 |
| failed item | 0 |
| review item | 16 |
| `theme_tags`가 있는 관광지 | 6,335 / 6,335 |
| `lcls_systm3`가 있는 관광지 | 6,335 / 6,335 |
| subtype 매핑 성공 관광지 | 6,334 / 6,335 |

관광지 품질 상태는 `passed` 6,321건, `review` 14건이다. 도시 추천의 후보 근거로 쓰기에는 통계적으로 충분하다.

### 2.2 현재 관광지 테마 분포

상위 관광지 테마는 다음과 같다.

| 테마 | 관광지 수 |
|---|---:|
| 역사·전통 | 3,236 |
| 자연·트레킹 | 1,930 |
| 바다·해안 | 547 |
| 예술·감성 | 462 |
| 온천·휴양 | 160 |

현재 관광지 분류 매핑에는 Lovv 6대 테마 중 `미식·노포`가 없다. 따라서 관광지만으로 도시를 추천하면 음식 선호 개인화는 직접 반영하기 어렵다. 음식 선호까지 도시 추천에 넣으려면 식당 데이터 또는 별도 미식 POI 데이터가 필요하다.

### 2.3 기존 파이프라인 적합성

- `src/kr_details_pipeline/domain_preprocess.py`는 관광지를 `PK = CITY#{city_name_en}`, `SK = ATTRACTION#{content_id}` 형태로 만들고 `theme`, `theme_tags`, `lcls_systm3`, `attraction_subtype_*`, 좌표, 주소, 설명을 보존한다.
- `src/kr_details_pipeline/handlers/domain_loader_handler.py`는 raw S3 JSON 하나를 전처리한 뒤 `TourKoreaDomainData`에 `load_items`를 적재한다.
- `src/kr_vector_index/export.py`는 `quality_status == passed`인 `city/city_metadata/attraction/festival`만 벡터화 대상으로 내보낸다.
- `src/kr_vector_index/chunks.py`는 `city_id`, `city_name_en`, `entity_type`, `place_id`, `theme_tags`, `class_tags`, 좌표, `ddb_pk`, `ddb_sk`를 S3 Vector metadata에 넣는다.
- `src/kr_vector_index/metadata.py`의 metadata allowlist에도 `theme_tags`, `class_tags`, `city_id`, `entity_type`, 좌표가 포함되어 있다.

이 구조 덕분에 벡터 검색 결과를 도시별로 group-by하고, DynamoDB에서 같은 도시의 관광지를 확장한 뒤, 테마 기반 근거 점수를 계산할 수 있다.

## 3. 추천 구조 제안

### 3.1 도시 추천 실행 흐름

```text
User Query
  -> query embedding
  -> S3 Vector QueryVectors
  -> attraction/festival/city 후보 획득
  -> ddb_pk/ddb_sk로 DynamoDB 정본 재조회
  -> city_id 또는 PK 기준 도시별 group-by
  -> 같은 도시의 관광지 추가 확장
  -> 도시별 evidence score + personalization score 계산
  -> 상위 도시와 대표 관광지 근거 반환
```

기존 `docs/reports/s3_vector_graphrag_usage_report.md`의 VectorRAG + DynamoDB graph expansion 방향과 일치한다.

### 3.2 개인화 입력

사용자별 테마 가중치는 다음처럼 별도 입력으로 다루는 것이 좋다.

```json
{
  "user_id": "USER#123",
  "theme_weights": {
    "역사·전통": 0.8,
    "자연·트레킹": 0.5,
    "바다·해안": 0.2
  },
  "updated_at": "2026-06-25T00:00:00Z",
  "source": "recommendation_history"
}
```

이 값은 데이터 수집 저장소가 아니라 Backend 또는 추천 서비스의 사용자 프로필/추천 이력 저장소에 두는 편이 맞다. `02_lovv_data_collect`는 `theme_tags`가 붙은 근거 데이터를 제공하고, retrieval layer는 요청 시 받은 가중치로 점수를 계산하면 된다.

### 3.3 도시 점수 예시

초기 점수식은 단순하고 설명 가능하게 시작하는 것이 좋다.

```text
city_score =
  0.35 * vector_seed_score
  + 0.25 * attraction_evidence_score
  + 0.20 * personalized_theme_score
  + 0.10 * theme_coverage_score
  + 0.10 * source_completeness_score
```

`personalized_theme_score`는 도시 안의 상위 관광지 N개에 대해 다음처럼 계산한다.

```text
attraction_theme_score = sum(user_theme_weight[t] for t in attraction.theme_tags)
city_personalized_theme_score = capped_average(top_n(attraction_theme_score, n=5))
```

도시별 관광지 수가 많은 곳이 무조건 유리해지는 것을 막기 위해 `sum`보다 `top_n average`, `log count`, `cap`을 쓰는 편이 안전하다.

## 4. 이전 추천 테마를 가중치로 쓸 때의 주의점

`이전에 추천받은 관광지`는 사용자가 좋아했다는 뜻이 아닐 수 있다. 추천 노출만으로 강한 선호를 만들면 기존 추천이 다음 추천을 계속 강화하는 피드백 루프가 생긴다.

권장 방식은 다음이다.

| 이벤트 | 가중치 반영 |
|---|---:|
| 추천 노출만 됨 | 약한 양수, 짧은 TTL |
| 클릭/상세 보기 | 중간 양수 |
| 저장/좋아요/일정 추가 | 강한 양수 |
| 숨김/관심 없음 | 음수 |

추천 노출만 사용할 수 있다면 `recommended` 이벤트의 가중치를 낮게 두고, 7~30일 decay를 적용하는 것이 좋다. 장기 개인화는 클릭, 저장, 실제 일정 추가 같은 사용자 행동 신호가 들어온 뒤 강화해야 한다.

## 5. 구현 시 필요한 최소 추가 요소

### 5.1 전처리/적재

현재 로컬 드라이런 기준으로 관광지 전처리는 가능하다. 운영 반영 시에는 다음이 필요하다.

1. `data/kr/details` 전체를 S3 raw prefix로 업로드하거나 현재 로컬 파일 기준 batch loader를 별도 실행한다.
2. `domain_loader_handler` 또는 동일 로직의 batch 실행으로 `TourKoreaDomainData`를 적재한다.
3. `kr-vector-index` build로 `quality_status == passed` item을 S3 Vector에 재색인한다.
4. 벡터 manifest와 DynamoDB item count를 비교해 누락을 확인한다.

### 5.2 추천/retrieval layer

새 모듈은 기존 보고서 제안처럼 `src/kr_graphrag/`로 분리하는 것이 좋다.

```text
src/kr_graphrag/
├── retrieve.py  # QueryVectors + DynamoDB rehydration
├── graph.py     # same city/theme/month expansion
├── score.py     # city score, personalization score
└── pack.py      # LLM 근거 JSON 생성
```

초기에는 Lambda보다 CLI 또는 테스트 가능한 함수로 먼저 검증하는 편이 좋다. 개인화 점수는 튜닝이 필요하므로 CloudWatch 로그만으로 조정하기 어렵다.

## 6. 주요 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| 관광지 테마가 5개에 치우침 | `미식·노포` 개인화 불가 | 식당/미식 POI 데이터와 결합하거나 음식 테마는 관광지 기반 점수에서 제외 |
| 추천 노출 기반 피드백 루프 | 같은 테마 반복 추천 | 노출 이벤트는 약한 가중치, decay, diversity penalty 적용 |
| S3 Vector metadata 2KB 제한 | 사용자 가중치 저장 불가 | 사용자별 가중치는 metadata에 넣지 않고 런타임 re-rank에서 사용 |
| 도시별 관광지 수 편차 | 대형 관광 도시가 과대평가 | 도시 점수에서 top-N 평균, cap, normalized coverage 사용 |
| review 상태 item 제외 | 일부 장소 누락 | `quality_status=review`는 운영 추천에서 제외하고 품질 리포트로 보완 |
| LLM hallucination | 없는 근거 생성 | `place_id`, `ddb_pk`, `ddb_sk`, `theme_matches`가 있는 후보만 LLM에 전달 |

## 7. 권장 다음 단계

1. `data/kr/details` 전체 전처리 결과를 실제 적재 기준으로 확정한다.
2. 도시별 `theme_profile` 집계 리포트를 만든다.
   - 예: `city_id`, `theme_counts`, `top_attractions_by_theme`, `quality_counts`
3. `theme_weights`를 입력으로 받는 `score_city_candidates()`를 먼저 순수 함수로 구현한다.
4. 샘플 사용자 프로필 3~5개로 같은 query에 도시 순위가 어떻게 바뀌는지 batch evaluation을 만든다.
5. 점수 breakdown을 응답에 포함해 “왜 이 도시가 추천됐는지”를 관광지 근거로 설명한다.

## 8. 최종 판단

관광지 데이터를 도시 추천의 근거로 삼고, 이전 추천 관광지의 테마를 개인화 가중치로 쓰는 것은 현재 구조에서 가능하다. 핵심은 `theme_tags`를 검색 필터로만 보지 말고, 도시별 관광지 evidence를 집계하는 re-ranking 신호로 쓰는 것이다.

즉시 구현 가능한 범위는 다음이다.

- 전처리: 기존 `kr_details_pipeline.domain_preprocess` 재사용 가능
- 적재: 기존 `TourKoreaDomainData` item 구조 재사용 가능
- 검색: 기존 S3 Vector metadata 재사용 가능
- 개인화: 신규 retrieval/score layer에서 `theme_weights` 기반 재랭킹 필요

구조 변경은 크지 않지만, 추천 품질을 위해서는 사용자 행동 이벤트와 도시별 테마 프로필 집계가 반드시 함께 설계되어야 한다.
