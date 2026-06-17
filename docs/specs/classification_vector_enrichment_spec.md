# Spec: Classification Dict 기반 Class-Aware Vector Enrichment

> PRD: `docs/classification_vector_enrichment_prd.md`
> 관련 구현: `src/kr_details_pipeline/domain_preprocess.py`, `src/kr_vector_index/chunks.py`, `src/kr_vector_index/metadata.py`
> Status: Draft
> Created: 2026-06-11
> Execution mode: Sequential Mode

## 1. Summary

`classification_dict.json`의 class/category/theme 값을 기존 KR domain preprocessing과 S3 Vector chunk 생성 경로에 연결한다.

구현 방향은 새 classification 전용 모듈을 추가하는 것이 아니라, 기존 `kr_details_pipeline`의 전처리 결과에 T 계열 필드를 병합하고, `kr_vector_index`가 해당 값을 embedding text와 metadata에 함께 포함하도록 하는 것이다.

## 2. Goals

1. classification dict 입력을 optional로 받아 기존 전처리 결과에 병합한다.
2. restaurant/attraction/festival item의 기존 T 계열 필드를 보강한다.
3. vector chunk 생성 시 class 값을 `embedding_text`, `class_tags`, `theme_tags`에 반영한다.
4. S3 Vector metadata allowlist에 `class_tags`를 포함한다.
5. 기존 vector build Lambda가 class-aware vector를 별도 경로 없이 생성할 수 있게 한다.

## 3. Non-Goals

- 새 `src/kr_classification_update` 모듈 추가
- DynamoDB scan 기반 대량 후처리 updater 구현
- item 삭제 또는 vector 삭제
- classification dict 원본을 workspace 밖 경로에서 직접 읽기
- GraphRAG Agent 본체 구현
- 전체 재색인을 한 번의 Lambda 실행으로 수행

## 4. Existing Code Context

### 4.1 Domain preprocessing

`src/kr_details_pipeline/domain_preprocess.py`

- `DOMAIN_KEYS`가 DynamoDB 적재 가능한 필드를 제한한다.
- restaurant는 `restaurant_category`, `cuisine_tags`를 생성한다.
- attraction은 `theme`, `theme_tags`, `season_tags`를 생성한다.
- festival은 `season`, `season_tags`, `visit_months`를 생성한다.
- `_build_domain_item()`이 entity별 item 생성의 중심이다.

### 4.2 DynamoDB load

`src/kr_details_pipeline/load.py`

- `_normalize_item()`은 legacy processed payload 적재 시 `theme`, `theme_tags`, `season_tags`를 유지한다.
- 신규 domain preprocessing 경로는 이미 projected item을 `put_item`으로 적재한다.

### 4.3 Vector chunk

`src/kr_vector_index/chunks.py`

- `build_embedding_text()`가 rich text를 생성한다.
- `build_chunk()`가 S3 Vector metadata를 생성한다.
- `_tags()`가 `theme_tags`, `season_tags`, `restaurant_category`, `theme`를 병합한다.

### 4.4 Metadata validation

`src/kr_vector_index/metadata.py`

- filterable metadata allowlist와 2KB 예산 검사를 수행한다.
- `class_tags`는 filterable metadata로 추가한다.

## 5. Data Contract

### 5.1 Classification input

classification dict entry는 최종 구현 전에 실제 JSON 구조 확인이 필요하다. 현재 spec은 다음 형태를 수용 가능한 입력 계약으로 둔다.

```json
{
  "<content_id_or_entity_id>": {
    "class": "date_course",
    "category": "walk",
    "theme": "scenery",
    "tags": ["photo_spot"]
  }
}
```

또는 entity type별 nested 형태:

```json
{
  "attraction": {
    "300": {
      "class": "date_course",
      "tags": ["photo_spot"]
    }
  }
}
```

### 5.2 DynamoDB output fields

| Entity | Fields |
| --- | --- |
| restaurant | `restaurant_category`, `cuisine_tags`, `theme_tags` |
| attraction | `theme`, `theme_tags`, `season_tags` |
| festival | `season_tags`, `visit_months`, optional `theme_tags` |

### 5.3 Vector metadata

```json
{
  "class_tags": ["date_course", "walk", "scenery", "photo_spot"],
  "theme_tags": ["bridge", "night_view", "date_course", "walk", "scenery", "photo_spot"]
}
```

### 5.4 Vector embedding text

```text
이름: 월영교
유형: 관광지
도시:  (Andong)
지역:
분류: date_course, walk, scenery, photo_spot
테마: night_view
설명: 야간 경관 명소
```

## 6. Functional Requirements

| ID | Requirement |
| --- | --- |
| FR-01 | `domain-preprocess` CLI에 optional `--classification-dict` 인자를 추가한다. |
| FR-02 | classification dict가 없으면 기존 output과 동일해야 한다. |
| FR-03 | classification dict가 있으면 `_build_domain_item()`에서 entity별 T 계열 필드에 병합한다. |
| FR-04 | 병합 시 빈 값과 중복 값을 제거한다. |
| FR-05 | `kr_vector_index.chunks`는 `class_tags`, `classification_tags`, `category_tags`, `cuisine_tags`, `classification` 값을 class tags로 정규화한다. |
| FR-06 | class tags는 `embedding_text`의 `분류` 라인과 metadata `class_tags`에 포함된다. |
| FR-07 | class tags는 `theme_tags`에도 병합되어 기존 theme filter와 함께 동작한다. |
| FR-08 | metadata allowlist에 `class_tags`를 포함하고 2KB budget 검사를 유지한다. |

## 7. Implementation Plan

### Step 1: Vector layer 반영

이미 반영된 기준:

- `metadata.py`
  - `FILTERABLE_METADATA_KEYS`에 `class_tags` 추가
- `chunks.py`
  - `_class_tags()` 추가
  - `_string_values()` 추가
  - `embedding_text`에 `분류` 라인 추가
  - metadata `class_tags` 추가
  - `_tags()`가 class tags를 병합
- `tests/test_chunks.py`
  - class 값이 embedding text, `class_tags`, `theme_tags`에 반영되는 테스트 추가

### Step 2: Domain preprocessing 입력 연결

대상 파일:

- `src/kr_details_pipeline/domain_preprocess.py`
- `src/kr_details_pipeline/cli.py`
- `src/kr_details_pipeline/tests/test_domain_preprocess.py`

작업:

1. classification dict loader helper를 `domain_preprocess.py` 내부에 추가한다.
2. `preprocess_city_file()` / `preprocess_city_payload()`에 optional classification map 인자를 추가한다.
3. `_build_domain_item()`에서 `content_id`, `entity_id`, `entity_type` 기준으로 classification entry를 찾는다.
4. restaurant/attraction/festival별 T 계열 필드에 병합한다.
5. `domain-preprocess` CLI에 `--classification-dict` 옵션을 추가한다.

### Step 3: Lambda loader 연결

대상 파일:

- `src/kr_details_pipeline/handlers/domain_loader_handler.py`

작업:

1. event에서 `classification_dict_s3_uri` 또는 `classification_dict_key`를 optional로 받는다.
2. 지정된 경우 S3에서 classification dict를 읽어 전처리에 전달한다.
3. 지정되지 않은 경우 기존 동작을 유지한다.

### Step 4: Vector 재생성

classification이 반영된 DynamoDB item을 기준으로 `kr-vector-index` Lambda를 city 단위로 실행한다.

```json
{
  "command": "build",
  "dry_run": false,
  "city_pk": "CITY#Andong"
}
```

## 8. Acceptance Criteria

- [ ] classification dict 미지정 시 기존 domain preprocessing 테스트가 그대로 통과한다.
- [ ] classification dict 지정 시 restaurant `restaurant_category`/`cuisine_tags`가 병합된다.
- [ ] classification dict 지정 시 attraction `theme`/`theme_tags`가 병합된다.
- [ ] classification dict 지정 시 festival `season_tags`/`visit_months` 보강 정책이 적용된다.
- [ ] vector chunk에 `분류` 라인이 생성된다.
- [ ] vector metadata에 `class_tags`가 생성된다.
- [ ] vector metadata `theme_tags`에 class tags가 병합된다.
- [ ] `python -m pytest src\kr_details_pipeline\tests src\kr_vector_index\tests`가 통과한다.
- [ ] `terraform validate`가 통과한다.
- [ ] Lambda dry-run에서 class-aware vector 생성이 확인된다.

## 9. Verification Commands

```powershell
python -m pytest src\kr_vector_index\tests
python -m pytest src\kr_details_pipeline\tests
python -m py_compile src\kr_vector_index\chunks.py src\kr_vector_index\metadata.py
terraform validate
```

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| 실제 classification dict 구조가 spec 가정과 다름 | 구현 전 JSON 구조를 workspace 내부 복사본으로 확인하고 loader를 구조별로 분기 |
| metadata 2KB 초과 | class tags 수를 제한하거나 filterable `class_tags`를 compact |
| 기존 theme를 잘못 덮어씀 | 기본 정책은 병합, 덮어쓰기 금지 |
| 전체 vector 재적재 시간 초과 | city 단위 Lambda 실행 |
| class 값이 너무 세분화되어 검색 품질 저하 | dry-run report와 샘플 query evaluation으로 class 값 정규화 |

## 11. Change History

| Version | Date | Change |
| --- | --- | --- |
| v0.1 | 2026-06-11 | classification dict 기반 T 필드 병합과 class-aware vector 생성 spec 초안 |
