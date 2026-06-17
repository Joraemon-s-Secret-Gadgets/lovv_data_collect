# CodeRabbitAI 리뷰 반영 계획

> 작성일: 2026-06-11
> 대상 PR: upstream `Joraemon-s-Secret-Gadgets/lovv_data_collect#2`
> 참고 PR: 잘못 생성된 fork 내부 PR `nobrain711/lovv_data_collect#1` (닫음)

## 1. 상황 정리

처음 PR을 잘못 생성해 fork 내부 PR `nobrain711/lovv_data_collect#1`에 CodeRabbitAI 리뷰가 붙었다.

해당 PR은 실제 리뷰 대상이 아니므로 닫았다.

실제 리뷰 대상은 upstream PR이다.

```text
https://github.com/Joraemon-s-Secret-Gadgets/lovv_data_collect/pull/2
```

현재 upstream PR에는 CodeRabbitAI의 상세 코드 리뷰가 없고, `cr-gpt[bot]`의 `OPENAI_API_KEY` secret 누락 댓글만 있다.

## 2. CodeRabbitAI 지적 내용

잘못 생성된 fork 내부 PR에 붙은 CodeRabbitAI의 실질 지적은 다음 1건이다.

| 항목 | 상태 | 내용 |
| --- | --- | --- |
| Docstring Coverage | Warning | docstring coverage가 `1.82%`로 낮고, 요구 기준 `80.00%`에 미달 |

Inline code comment나 파일/라인 단위 버그 지적은 확인되지 않았다.

## 3. 반영 판단

이 지적은 실제 버그나 보안 취약점은 아니지만, 새로 추가한 vector pipeline 코드가 운영 Lambda와 AWS 적재 경로를 포함하므로 public 함수의 책임을 명확히 하는 편이 좋다.

단, 테스트 함수와 내부 helper까지 무리하게 docstring을 추가하면 노이즈가 커진다. 따라서 다음 기준으로 반영한다.

## 4. 반영 범위

### 4.1 docstring 추가 대상

새로 추가한 `src/kr_vector_index`의 public API 중심으로 추가한다.

| 파일 | 대상 |
| --- | --- |
| `export.py` | `should_vectorize`, `iter_gsi3_items`, `export_items`, `count_by_entity_type` |
| `chunks.py` | `VectorChunk`, `build_chunk`, `build_chunks`, `build_embedding_text` |
| `metadata.py` | `MetadataValidationError`, `validate_metadata`, `compact_metadata` |
| `embed.py` | `EmbeddingError`, `embed_text`, `embed_chunks` |
| `upsert.py` | `chunked`, `build_vector_record`, `put_vectors_cli`, `put_vectors_sdk`, `build_vector_records` |
| `manifest.py` | `build_manifest`, `write_json` |
| `cli.py` | `parse_args`, `session`, `main` |
| `handlers/vector_index_handler.py` | `handler` |
| `console_test.py` | console smoke test public helpers |

### 4.2 docstring 제외 대상

다음은 제외한다.

| 대상 | 제외 이유 |
| --- | --- |
| `tests/` 하위 테스트 함수 | 테스트명 자체가 동작 설명이며 docstring 추가 시 가독성 저하 |
| `_private_helper` 함수 | 내부 구현 세부이며 과도한 주석 가능성 |
| 단순 dataclass field별 설명 | 현재 타입과 생성 로직으로 충분 |

## 5. 구현 계획

1. `src/kr_vector_index` public 함수와 class에 짧은 docstring을 추가한다.
2. docstring은 함수 책임, 입력/출력 의미, AWS side effect 여부를 중심으로 작성한다.
3. 로직 변경은 하지 않는다.
4. 삭제 방지 원칙을 유지한다.
   - `DeleteVectors` 권한/명령은 추가하지 않는다.
   - console smoke test는 계속 vector를 삭제하지 않는다.
5. 검증을 실행한다.
   - `python -m pytest src\kr_vector_index\tests`
   - `python -m py_compile src\kr_vector_index\*.py src\kr_vector_index\handlers\vector_index_handler.py`
   - `terraform validate`
   - 필요 시 `terraform plan`
6. Conventional Commit으로 커밋한다.
   - 예상 메시지: `docs(vector-index): add pipeline API docstrings`
7. 같은 브랜치 `feat-vector-index-graphrag`에 push해 upstream PR `#2`를 업데이트한다.

## 6. classification_dict.json DynamoDB 업데이트 계획

사용자가 제공한 `classification_dict.json`을 DynamoDB `TourKoreaDomainData`에 반영하는 작업도 후속 반영 범위에 포함한다.

원본 파일은 현재 workspace 밖 경로에 있다.

```text
C:/Users/qazx9/OneDrive/바탕 화면/classification_dict.json
```

따라서 구현 시에는 원본을 직접 참조하지 않고, 먼저 workspace 내부의 검토 가능한 입력 경로로 복사한 뒤 처리한다.

### 6.1 목표

`classification_dict.json`의 분류 정보를 DynamoDB item에 업데이트해, 이후 S3 Vector chunk 생성과 GraphRAG retrieval에서 더 정확한 T 계열 필드를 사용할 수 있게 한다.

여기서 T 계열 필드는 현재 `src` 코드에 이미 존재하는 theme/type/category 계열 필드를 의미한다.

```text
theme
theme_tags
restaurant_category
cuisine_tags
season_tags
```

새 분류 전용 모듈이나 별도 DynamoDB entity를 만들지 않고, 기존 전처리와 적재 경로에 붙인다.

### 6.2 사전 확인

1. `src` 전체 코드 기준 분류 필드 흐름 확인
   - `src/kr_details_pipeline/domain_preprocess.py`
     - `DOMAIN_KEYS`가 DynamoDB 적재 가능 필드를 제한한다.
     - restaurant는 `restaurant_category`, `cuisine_tags`를 사용한다.
     - attraction은 `theme`, `theme_tags`, `season_tags`를 사용한다.
     - festival은 `season`, `season_tags`, `visit_months`를 사용한다.
   - `src/kr_details_pipeline/load.py`
     - legacy processed payload 적재 시 `theme`, `theme_tags`, `season_tags`를 유지한다.
   - `src/kr_vector_index/chunks.py`
     - vector metadata와 embedding text가 `theme_tags`, `restaurant_category`, `theme`, `season_tags`를 읽는다.
2. JSON 구조 확인
   - top-level key 형식
   - content id 또는 entity id 매핑 방식
   - city/attraction/restaurant/festival별 분류 필드
   - theme/category/tag 필드명
3. DynamoDB item 식별자와 매핑 가능 여부 확인
   - `PK`
   - `SK`
   - `content_id`
   - `entity_id`
   - `entity_type`
4. 기존 item 필드와 충돌 여부 확인
   - `theme_tags`
   - `restaurant_category`
   - `cuisine_tags`
   - `season_tags`
   - `category`
   - `classification`
   - `source_type`

### 6.3 구현 방식

새 모듈은 추가하지 않는다.

기존 모듈에 최소 변경으로 붙인다.

| 파일 | 변경 방향 |
| --- | --- |
| `src/kr_details_pipeline/domain_preprocess.py` | classification dict를 optional 입력으로 받아 `_build_domain_item`에서 T 계열 필드에 병합 |
| `src/kr_details_pipeline/cli.py` | `domain-preprocess` 명령에 `--classification-dict` 옵션 추가 |
| `src/kr_details_pipeline/handlers/domain_loader_handler.py` | 필요 시 S3/이벤트 기반 classification dict 위치를 받아 전처리에 전달 |
| `src/kr_details_pipeline/tests/test_domain_preprocess.py` | classification dict가 restaurant/attraction/festival T 필드에 반영되는지 테스트 |
| `src/kr_vector_index/chunks.py` | 새 T 필드가 기존 `theme_tags`/category 경로로 들어오면 별도 변경 없이 반영되는지 확인. 부족하면 `_tags` 병합만 보강 |

기본 전략은 **전처리 시점에 T 필드를 완성하고 DynamoDB에 PutItem으로 적재**하는 것이다. 이미 적재된 item을 별도 updater로 후처리하는 방식은 우선순위에서 제외한다.

권장 CLI:

```powershell
$env:PYTHONPATH='src'
python -m kr_details_pipeline.cli domain-preprocess `
  --raw-file data/KR/details/Andong.json `
  --output-dir data/KR/processed/domain `
  --table-name TourKoreaDomainData `
  --classification-dict data/KR/classification/classification_dict.json
```

기존 S3 Raw 전체를 기준으로 다시 적재할 때는 현재 domain loader 경로에 같은 옵션을 연결한다.

```powershell
aws lambda invoke `
  --function-name kr-domain-loader `
  --cli-binary-format raw-in-base64-out `
  --payload '{"bucket":"lovv-data-pipeline-dev-925273580929","key":"raw/KR/...json","classification_dict_s3_uri":"s3://lovv-data-pipeline-dev-925273580929/config/KR/classification/classification_dict.json"}' `
  response.json `
  --profile skn26_final `
  --region us-east-1
```

### 6.4 업데이트 정책

| 항목 | 정책 |
| --- | --- |
| 기존 필드 덮어쓰기 | 기본 금지. classification 값은 기존 T 필드에 병합 |
| 신규 분류 전용 필드 | 기본 추가하지 않음 |
| restaurant | `restaurant_category`, `cuisine_tags`에 병합 |
| attraction | `theme`, `theme_tags`, `season_tags`에 병합 |
| festival | `season_tags`, `visit_months` 보강 가능 여부만 검토 |
| 빈 값 | DynamoDB에 쓰지 않음 |
| 매칭 실패 | review report에 기록하고 기존 값 유지 |
| 삭제 | 어떤 item도 삭제하지 않음 |
| vector 삭제 | S3 Vector 삭제 없음 |

### 6.5 DynamoDB 업데이트 방식

기본 방식은 별도 `UpdateItem` 후처리가 아니라, 기존 domain preprocessing 산출물에 T 필드를 반영한 뒤 `kr-domain-loader`의 기존 `PutItem` 적재 경로를 사용한다.

반영 대상 필드:

```text
theme_tags
theme
restaurant_category
cuisine_tags
season_tags
visit_months
```

조건:

- `PK`와 `SK`는 기존 `domain_preprocess.py` 생성 규칙을 그대로 사용한다.
- `DOMAIN_KEYS`에 포함되지 않은 필드는 DynamoDB에 적재하지 않는다.
- classification dict 값은 기존 `_assigned_theme`, `cat3`, intro field보다 우선순위를 어떻게 둘지 dry-run에서 비교 후 확정한다.
- 후처리 `UpdateItem`이 꼭 필요한 경우에만 별도 작업으로 분리하고, 이 경우도 신규 모듈이 아니라 기존 `kr_details_pipeline.load`에 helper를 추가한다.

### 6.6 검증 계획

1. dry-run report 생성
   - 총 JSON entry 수
   - raw record 매칭 성공 수
   - 매칭 실패 수
   - T 필드 병합 예정 count
2. 전처리 산출물 확인
   - `load/tour_korea_domain_items.jsonl`
   - restaurant의 `restaurant_category`, `cuisine_tags`
   - attraction의 `theme`, `theme_tags`
   - festival의 `season_tags`, `visit_months`
3. 샘플 item 재조회
   - restaurant 3건
   - attraction 3건
   - festival 3건
   - city 3건
4. 단위 테스트
   - classification dict load/schema validation
   - content id 기준 matching
   - T 필드 병합
   - 빈 값 제외
   - 기존 필드 보호
5. 실제 적용 후 DynamoDB count 재확인
6. vector 영향 확인
   - `kr-vector-index` Lambda dry-run으로 chunk text/metadata 반영 여부 확인
   - 필요 시 city 단위 S3 Vector 재적재

### 6.7 산출물

| 파일 | 목적 |
| --- | --- |
| `data/KR/classification/classification_dict.json` | workspace 내부 검토용 입력 |
| `docs/reports/classification_dynamodb_update_plan.md` | 세부 계획 |
| `docs/reports/classification_dynamodb_update_result.md` | 적용 결과 |
| `src/kr_details_pipeline/domain_preprocess.py` | 기존 전처리 단계에서 T 필드 병합 |
| `src/kr_details_pipeline/cli.py` | classification dict 옵션 추가 |
| `src/kr_details_pipeline/handlers/domain_loader_handler.py` | Lambda 경로 옵션 연결 |
| `src/kr_details_pipeline/tests/` | 기존 전처리 테스트 확장 |

### 6.8 완료 기준

- dry-run에서 매칭/변경 예정 항목이 명확히 보고된다.
- 실제 apply 후 DynamoDB item의 기존 T 계열 필드에 분류 정보가 반영된다.
- 기존 item 삭제나 vector 삭제가 발생하지 않는다.
- vector Lambda dry-run에서 새 분류가 embedding text 또는 metadata에 반영됨을 확인한다.
- 필요 시 변경된 city만 S3 Vector에 재적재한다.

## 7. 보류 사항

`cr-gpt[bot]`의 `OPENAI_API_KEY` secret 누락은 코드 변경으로 해결할 수 없다. upstream repository admin이 GitHub Actions secret을 설정해야 한다.

따라서 이 항목은 PR 코드 반영 대상이 아니라 repository 설정 작업으로 분리한다.

## 8. 완료 기준

- 새 vector pipeline public 함수에 docstring이 추가된다.
- `classification_dict.json` DynamoDB 업데이트 계획이 별도 작업 단위로 정리된다.
- 테스트가 기존과 동일하게 통과한다.
- Terraform 검증이 깨지지 않는다.
- upstream PR `#2`에 추가 커밋이 반영된다.
- 잘못 생성한 fork 내부 PR은 닫힌 상태로 유지된다.
