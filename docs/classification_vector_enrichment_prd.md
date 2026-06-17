# Lovv KR Classification Vector Enrichment PRD

> 문서 버전: v0.1
> 문서 상태: Draft
> 작성일: 2026-06-11
> 범위: `classification_dict.json` 기반 T 계열 분류값을 DynamoDB와 S3 Vector chunk에 반영하는 요구사항
> 관련 문서: `docs/s3_vector_index_prd.md`, `docs/specs/s3_vector_index_spec.md`, `docs/reports/coderabbit_review_response_plan.md`

## 1. 목적

`classification_dict.json`의 class/category/theme 정보를 한국 관광 도메인 데이터의 T 계열 필드에 반영하고, S3 Vector 생성 시 class 정보를 embedding text와 metadata에 함께 포함한다.

이 작업의 목표는 GraphRAG 검색에서 단순 키워드 유사도뿐 아니라 장소 분류, 테마, 음식/관광 유형을 함께 검색 근거로 사용할 수 있게 하는 것이다.

## 2. 배경

현재 KR vector pipeline은 DynamoDB `TourKoreaDomainData`를 원천으로 `city`, `attraction`, `restaurant`, `festival` item을 export하고, `theme_tags`, `restaurant_category`, `season_tags` 등을 사용해 rich embedding text와 S3 Vector metadata를 만든다.

하지만 외부 분류 사전(`classification_dict.json`)에서 관리되는 class 값은 아직 전처리/벡터화 계약에 명시되어 있지 않다. 따라서 분류 사전 값을 기존 T 계열 필드에 병합하고, vector chunk에도 class 정보를 포함하는 요구사항을 추가한다.

## 3. 용어

| 용어 | 정의 |
| --- | --- |
| classification dict | 사용자가 제공한 `classification_dict.json`. content/entity별 class/category/theme/tag 정보를 담는 외부 분류 사전 |
| T 계열 필드 | theme/type/category 성격의 필드. 현재 코드 기준 `theme`, `theme_tags`, `restaurant_category`, `cuisine_tags`, `season_tags`, `visit_months` |
| class tags | vector 생성 시 별도 metadata로 저장되는 분류 태그 목록. S3 Vector metadata key는 `class_tags` |
| class-aware vector | embedding text와 metadata에 class/category/theme 분류값이 함께 포함된 vector |

## 4. 범위

### 4.1 포함

- `classification_dict.json` 값을 기존 `kr_details_pipeline` 전처리 경로에 연결한다.
- 새 DynamoDB entity나 별도 classification 전용 모듈을 만들지 않는다.
- 기존 T 계열 필드에 class/category/theme 값을 병합한다.
- S3 Vector chunk 생성 시 다음 값을 함께 생성한다.
  - embedding text의 `분류: ...` 라인
  - metadata의 `class_tags`
  - metadata의 `theme_tags` 병합값
- 기존 vector build Lambda가 class-aware chunk를 그대로 embedding/upsert할 수 있게 한다.

### 4.2 제외

- `classification_dict.json` 원본 파일을 workspace 밖 경로에서 직접 읽는 동작
- DynamoDB item 삭제
- S3 Vector 삭제
- 별도 그래프 DB 도입
- Agent/LLM 응답 생성 구현
- 신규 `src/kr_classification_update` 같은 별도 업데이트 모듈 추가

## 5. 데이터 원천과 저장 위치

원본 파일은 사용자가 제공한다.

```text
C:/Users/qazx9/OneDrive/바탕 화면/classification_dict.json
```

구현 시에는 해당 파일을 직접 참조하지 않고, workspace 내부 검토 경로로 복사한 뒤 사용한다.

```text
data/KR/classification/classification_dict.json
```

## 6. 기능 요구사항

### FR-01 classification dict 입력

- `classification_dict.json`은 전처리 실행 시 optional 입력으로 받을 수 있어야 한다.
- 입력 경로는 CLI 옵션 또는 Lambda event/S3 URI로 전달한다.
- 파일이 없으면 기존 전처리 동작은 변하지 않아야 한다.

### FR-02 기존 T 계열 필드 병합

classification dict 값은 새 entity가 아니라 기존 T 계열 필드에 병합한다.

| Entity | 반영 필드 |
| --- | --- |
| restaurant | `restaurant_category`, `cuisine_tags`, `theme_tags` |
| attraction | `theme`, `theme_tags`, `season_tags` |
| festival | `season_tags`, `visit_months`, 필요 시 `theme_tags` |
| city/city_metadata | 도시 분류가 있는 경우 `theme_tags` 또는 city-level classification으로 검토 |

### FR-03 기존 필드 보호

- 기존 T 필드가 이미 있으면 기본적으로 덮어쓰지 않고 병합한다.
- 중복 값은 제거한다.
- 빈 문자열, 빈 리스트, `null`은 DynamoDB에 쓰지 않는다.
- classification 값과 기존 `_assigned_theme`, `cat3`, intro field의 우선순위는 dry-run report에서 비교 후 확정한다.

### FR-04 class-aware vector 생성

S3 Vector chunk 생성 시 DynamoDB item의 class 계열 값을 읽어 vector payload에 포함한다.

지원 입력 필드:

```text
class_tags
classification_tags
category_tags
cuisine_tags
classification
```

`classification`은 문자열, 리스트, dict를 지원한다. dict인 경우 다음 key를 읽는다.

```text
class
category
theme
type
tags
```

### FR-05 embedding text 반영

class 값이 존재하면 `embedding_text`에 다음 라인을 추가한다.

```text
분류: {class_tag_1}, {class_tag_2}, ...
```

### FR-06 metadata 반영

S3 Vector metadata에 `class_tags`를 추가한다.

```json
{
  "class_tags": ["date_course", "walk", "scenery"]
}
```

또한 `theme_tags`에는 기존 theme/category 값과 class tags를 병합한다.

### FR-07 GraphRAG 검색 호환성

GraphRAG retrieval layer는 다음 방식으로 class-aware vector를 활용할 수 있어야 한다.

- `theme_tags` 기반 테마 필터 검색
- `class_tags` 기반 분류 필터 검색
- vector embedding text에 포함된 `분류` 문맥 기반 semantic retrieval
- DynamoDB `ddb_pk`/`ddb_sk` 재조회로 정본 검증

### FR-08 보고서와 검증

classification dict 반영 시 다음 결과를 보고해야 한다.

- classification dict 총 entry 수
- raw/DynamoDB item 매칭 성공 수
- 매칭 실패 수
- T 필드 병합 수
- 샘플 item 변경 전/후
- vector dry-run에서 class 값 반영 여부

## 7. 비기능 요구사항

| 항목 | 요구 |
| --- | --- |
| 안전성 | DynamoDB item과 S3 Vector 삭제 금지 |
| 재현성 | classification dict + S3 Raw + DynamoDB로 같은 T 필드 결과를 재생성 가능 |
| 호환성 | classification dict가 없으면 기존 파이프라인 결과와 동일 |
| 메타데이터 제한 | `class_tags` 포함 후에도 filterable metadata 2KB 제한 통과 |
| 범위 제한 | 새 모듈보다 기존 `kr_details_pipeline`과 `kr_vector_index` 확장 우선 |

## 8. 수용 기준

- [ ] AC-01: classification dict가 없을 때 기존 domain preprocessing 결과가 변하지 않는다.
- [ ] AC-02: classification dict가 있으면 restaurant/attraction/festival의 T 계열 필드에 값이 병합된다.
- [ ] AC-03: 중복 class/theme 값이 제거된다.
- [ ] AC-04: vector chunk `embedding_text`에 `분류: ...` 라인이 포함된다.
- [ ] AC-05: vector metadata에 `class_tags`가 포함된다.
- [ ] AC-06: `theme_tags`에 class tags가 병합되어 검색 필터로 활용 가능하다.
- [ ] AC-07: `python -m pytest src\kr_vector_index\tests`가 통과한다.
- [ ] AC-08: `kr-vector-index` Lambda dry-run에서 class-aware chunk 생성이 확인된다.
- [ ] AC-09: 실제 vector upsert는 city 단위로만 실행하고, 삭제 동작은 포함하지 않는다.

## 9. 운영 흐름

```text
classification_dict.json 준비
  -> workspace 내부 data/KR/classification/ 경로에 복사
  -> domain-preprocess 실행 시 classification dict 전달
  -> T 계열 필드 병합
  -> TourKoreaDomainData 적재
  -> kr-vector-index dry-run으로 class-aware chunk 확인
  -> city 단위 S3 Vector 재적재
```

## 10. 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v0.1 | 2026-06-11 | classification dict 기반 T 계열 필드 병합과 class-aware vector 생성 요구사항 초안 |
