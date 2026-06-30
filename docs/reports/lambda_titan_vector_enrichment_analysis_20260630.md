# Lambda / Titan Vector Enrichment Analysis - 2026-06-30

## 결론

현재 상태에서 `kr-pipeline-vector` Lambda의 Titan embedding 모델 지정 자체는 수정할 필요가 없다.

코드와 live AWS 설정 모두 S3 Vector embedding에 Amazon 제공 모델인 `amazon.titan-embed-text-v2:0`를 사용하도록 되어 있다.

다만 Step Functions 운영 경로는 수정 또는 우회가 필요하다. 분석 당시 `VectorStage`는 전용 `kr-pipeline-vector` Lambda가 아니라 `kr-pipeline-loader` Lambda를 `vector-build` command로 호출했다. live CloudWatch에서 이 loader 경로는 900초 timeout을 기록했다.

## 확인한 사실

### Titan 모델

- Bedrock model: `amazon.titan-embed-text-v2:0`
- Provider: `Amazon`
- Input modality: `TEXT`
- Output modality: `EMBEDDING`
- Inference type: `ON_DEMAND`

이 모델은 vector embedding 생성용이다. `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `metadata_enrichment` 같은 의미 태그를 직접 생성하는 모델 경로가 아니다.

### 코드 경로

- `src/kr_vector_index/embed.py`
  - `EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"`
  - `embed_text()`가 Bedrock Runtime `invoke_model()`로 Titan embedding을 호출한다.

- `src/kr_vector_index/metadata.py`
  - `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `schema_version`은 allowlist에 있다.
  - 단, `metadata_enrichment.status == "succeeded"`일 때만 vector metadata에 포함된다.
  - 전체 `metadata_enrichment` 객체는 S3 Vector metadata에서 제외된다.

- `src/kr_details_pipeline/enrichment_engine.py`
  - 현재 enrichment 생성 기본 모델은 `openai.gpt-oss-120b-1:0`이다.
  - 즉 Titan embedding Lambda와 enrichment 생성은 별도 책임이다.

### Live Lambda 설정

`kr-pipeline-vector`

- Handler: `kr_vector_index.handlers.vector_index_handler.handler`
- Runtime: `python3.12`
- Timeout: `900`
- Memory: `1024`
- `DYNAMODB_TABLE=TourKoreaDomainDataV2`
- `VECTOR_BUCKET=lovv-vector-dev`
- `VECTOR_INDEX=kr-tour-domain-v2`

`kr-pipeline-loader`

- Handler: `kr_unified_pipeline.handlers.pipeline_handler.handler`
- Timeout: `900`
- Memory: `512`
- `DYNAMODB_TABLE=TourKoreaDomainDataV2`
- `VECTOR_BUCKET=lovv-vector-dev`
- `VECTOR_INDEX=kr-tour-domain-v2`

### Step Functions 경로

분석 당시 `infrastructure/terraform/step_functions.tf`의 `VectorStage`는 다음 Lambda를 호출했다.

- Resource: `aws_lambda_function.kr_pipeline_loader.arn`
- command: `vector-build`
- index_name: `var.kr_vector_index_name`

따라서 운영 Step Functions 실행은 전용 vector Lambda가 아니라 loader Lambda의 vector-build 분기를 사용한다.

### Live timeout 증거

CloudWatch `AWS/Lambda` 지표와 loader log report에서 다음이 확인됐다.

- 2026-06-29 23시대: `kr-pipeline-loader` max duration 약 `828,047 ms`
- 2026-06-30 00시대: `kr-pipeline-loader` duration `900,000 ms`, status `timeout`
- 같은 기간 `kr-pipeline-vector`는 유의미한 full build 실행 흔적이 거의 없다.

### Live data 상태

- `TourKoreaDomainDataV2` attraction count: `7,024`
- `metadata_enrichment` exists count: `0`
- `kr-tour-domain-v2` vector sample metadata에는 enrichment-derived keys가 없다.

현재 vector metadata에 enrichment 필드가 없는 직접 원인은 Lambda 모델 문제가 아니라 DynamoDB source item에 enrichment 필드가 없기 때문이다.

## 수정 필요 여부

### 1. Titan embedding 모델 때문에 Lambda를 수정해야 하는가?

아니오.

S3 Vector embedding 경로는 이미 Amazon Titan Embeddings V2를 사용한다. IAM도 `bedrock:InvokeModel` on `arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0` 권한을 포함한다.

### 2. S3 Vector metadata 반영 때문에 Lambda를 수정해야 하는가?

부분적으로는 아니오.

DynamoDB item에 다음 조건이 만족되면 현재 vector metadata builder가 enrichment-derived fields를 포함한다.

- `metadata_enrichment.status == "succeeded"`
- top-level `indoor_outdoor`
- top-level `vibe_tags`
- top-level `experience_tags`
- top-level `companion_fit`
- top-level `schema_version`

따라서 DynamoDB enrichment backfill이 먼저 완료되면, vector metadata inclusion 로직 자체는 추가 수정 없이 동작할 수 있다.

### 3. 운영 실행 경로 때문에 Lambda/Step Functions를 수정해야 하는가?

예.

현재 Step Functions의 `VectorStage`가 `kr-pipeline-loader`를 호출하고 있고, 이 경로는 live에서 900초 timeout을 냈다. full vector rebuild를 운영 경로로 안정화하려면 다음 중 하나가 필요하다.

1. `VectorStage`를 `kr-pipeline-vector` Lambda 호출로 바꾼다.
2. full rebuild를 Lambda 단일 실행으로 처리하지 않고 Step Functions Map 또는 city/batch 단위로 쪼갠다.
3. 현재 loader 경로를 유지한다면 최소한 vector-build 전용으로 memory를 늘리고, 진행 cursor와 partial upsert/resume을 지원해야 한다.

권장안은 1번과 2번의 조합이다. Lambda timeout은 최대 900초라 timeout 값만 더 늘릴 수 없다.

### 4. DynamoDB enrichment 적재를 Lambda로 해야 하는가?

현재는 선택 사항이다.

이미 로컬/CLI용 `scripts/backfill_enrichment.py`와 `src/kr_details_pipeline/enrichment_persistence.py`가 있다. 제한 실행과 검증 단계에서는 이 guarded runner를 쓰는 편이 안전하다.

하지만 운영 재실행 가능한 파이프라인으로 만들려면 별도 enrichment Lambda 또는 Step Functions Map 작업이 필요하다. 이 작업은 Titan embedding Lambda와 별도로 설계해야 한다. Titan Embeddings V2는 enrichment 태그를 생성하지 않는다.

## 권장 조치

1. 먼저 DynamoDB enrichment backfill을 제한 실행한다.
   - 예: 50건, 200건, 500건 순서
   - 성공 후 DynamoDB field count를 확인한다.

2. Step Functions의 `VectorStage` 실행 대상을 재검토한다.
   - 현재 loader Lambda는 timeout 증거가 있다.
   - 전용 `kr-pipeline-vector` Lambda를 쓰거나, batch/Map 구조로 분할한다.

3. DynamoDB에 enrichment 필드가 들어간 뒤 `kr-tour-domain-v2`를 다시 build한다.
   - 이때 Titan embedding은 기존 `amazon.titan-embed-text-v2:0` 경로를 유지한다.

4. full rebuild를 Lambda 단일 실행으로 밀어붙이지 않는다.
   - 900초 제한 때문에 batch/resume 설계가 더 안정적이다.

## 최종 판단

지금 당장 수정해야 하는 것은 Titan 모델 지정이 아니다.

수정이 필요한 것은 운영 orchestration이다. 특히 Step Functions가 전용 vector Lambda 대신 loader Lambda를 호출하는 구조와, 900초 안에 full rebuild를 끝내야 하는 단일 Lambda 실행 구조가 현재 위험 지점이다.

## 구현 반영 내역

2026-06-30에 repo 코드 기준으로 다음 변경을 반영했다.

- `infrastructure/terraform/step_functions.tf`
  - `VectorStage` 호출 대상을 `aws_lambda_function.kr_pipeline_loader.arn`에서 `aws_lambda_function.kr_pipeline_vector.arn`으로 변경했다.
  - vector handler가 지원하는 `command = "build"`를 사용하도록 변경했다.
  - V2 table, `EntityTypeDomainIndex`, S3 Vector bucket/index를 명시적으로 전달하도록 변경했다.

- `src/kr_vector_index/handlers/vector_index_handler.py`
  - 기본 DynamoDB table을 `TourKoreaDomainDataV2`로 변경했다.
  - 기본 S3 Vector index를 `kr-tour-domain-v2`로 변경했다.
  - DynamoDB export 시 `EntityTypeDomainIndex`를 기본 GSI로 사용하도록 `entity_index_name` 입력을 추가했다.

- `src/kr_vector_index/tests/test_vector_index_handler.py`
  - handler가 기본값으로 V2 table과 `EntityTypeDomainIndex`를 사용하는지 검증하는 테스트를 추가했다.

검증 결과:

- `uv run python -m pytest src/kr_vector_index/tests/test_vector_index_handler.py -q --basetemp .cache/pytest-tmp -p no:cacheprovider` 통과, 4 passed.
- `uv run python -m pytest src/kr_vector_index/tests/test_metadata.py src/kr_vector_index/tests/test_upsert.py src/kr_vector_index/tests/test_vector_index_handler.py -q --basetemp .cache/pytest-tmp -p no:cacheprovider` 통과, 25 passed.
- `uv run ruff check src/kr_vector_index/handlers/vector_index_handler.py src/kr_vector_index/tests/test_vector_index_handler.py` 통과.
- `uv run ruff format --check src/kr_vector_index/handlers/vector_index_handler.py src/kr_vector_index/tests/test_vector_index_handler.py` 통과.
- `terraform -chdir=infrastructure/terraform fmt -check -diff step_functions.tf` 통과.
- `terraform -chdir=infrastructure/terraform validate` 통과.

주의:

- 이 변경은 repo 코드와 Terraform 정의 수정까지만 포함한다.
- live AWS 배포, Terraform apply, Lambda 재배포, Step Functions 재실행은 아직 수행하지 않았다.
- DynamoDB에 enrichment field가 아직 없다면 vector rebuild를 실행해도 enrichment-derived metadata는 S3 Vector에 생기지 않는다.
