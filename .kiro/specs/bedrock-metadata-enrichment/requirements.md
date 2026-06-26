# Requirements Document

## Introduction

본 문서는 Lovv 여행 데이터 파이프라인에서 Bedrock LLM을 활용한 관광지 메타데이터 보강(Attraction Metadata Enrichment)과 축제 테마 재분류(Festival Theme Reclassification) 기능의 요구사항을 정의한다.

현재 파이프라인은 TourAPI 원천 데이터를 DynamoDB에 적재하고 S3 Vector index로 검색 가능하게 만드는 구조이다. 그러나 관광지의 감성·경험·동행 적합도 정보가 부족하고, 축제는 TourAPI의 `lclsSystm3` 분류 코드가 실제 행사 내용을 반영하지 못해 6대 테마 분류 정확도가 낮다.

이 기능은 두 가지 독립된 Bedrock 호출 단계를 도입한다:
1. 관광지(`entity_type="attraction"`) 전용 4개 메타데이터 필드 추출
2. 축제(`entity_type="festival"`) 전용 Lovv 6대 테마 재분류

## Glossary

- **Enrichment_Engine**: Bedrock LLM을 호출하여 관광지 메타데이터 4개 필드를 추출하는 모듈
- **Theme_Classifier**: Bedrock LLM을 호출하여 축제의 Lovv 6대 테마를 재분류하는 모듈
- **DynamoDB_Store**: 관광지·축제 item의 기준 데이터를 저장하는 DynamoDB 테이블
- **Vector_Metadata_Builder**: S3 Vector index의 filterable metadata를 구성하는 모듈
- **Classification_Dict**: `classification_dict.json` 파일 기반의 `lclsSystm3` 코드-테마 매핑 사전
- **Canonical_Taxonomy**: 시스템이 허용하는 유한한 태그 집합 (vibe_tags, experience_tags, companion_fit, 6대 테마)
- **Input_Hash**: Bedrock 호출 입력 필드의 정규화된 SHA-256 해시값으로 중복 호출 방지에 사용
- **Review_Queue**: 자동 분류에 실패하거나 근거 부족으로 수동 검수가 필요한 item을 모아두는 대기열
- **Lovv_6대_테마**: 바다·해안, 자연·트레킹, 미식·노포, 역사·전통, 예술·감성, 온천·휴양

## Requirements

### Requirement 1: 원천 분류 코드 보존

**User Story:** As a 데이터 엔지니어, I want TourAPI의 원천 분류 코드(`lclsSystm3`, `source_type`, `raw_s3_uri`)를 DynamoDB item에 보존하고 싶다, so that 이후 enrichment와 재분류의 입력 기준과 감사 추적이 가능하다.

#### Acceptance Criteria

1. WHEN 관광지 raw 데이터가 전처리될 때, THE DynamoDB_Store SHALL `lcls_systm3` 필드에 TourAPI `common.lclsSystm3` 값을 snake_case 문자열로 저장하되, `common.lclsSystm3`가 없으면 수집 record 최상위의 `lclsSystm3` 값을 대체로 사용한다
2. WHEN 축제 raw 데이터가 전처리될 때, THE DynamoDB_Store SHALL `lcls_systm3` 필드에 TourAPI `common.lclsSystm3` 값을 snake_case 문자열로 저장하되, `common.lclsSystm3`가 없으면 수집 record 최상위의 `lclsSystm3` 값을 대체로 사용한다
3. THE DynamoDB_Store SHALL `source_type` 필드에 수집 파이프라인 상수(최대 32자 영문 소문자+언더스코어)를 저장하고, `entity_type` 필드와 동일한 값을 사용하지 않는다
4. WHEN raw 객체가 S3에 저장된 후, THE DynamoDB_Store SHALL `raw_s3_uri` 필드에 `s3://{bucket}/{key}` 형식의 전체 S3 객체 경로를 최대 1024자 이내로 기록한다
5. IF `lcls_systm3` 값이 null이거나, 빈 문자열이거나, 해당 키가 원천 데이터에 존재하지 않으면, THEN THE DynamoDB_Store SHALL 해당 item의 `review_queues`에 `classification_review`를 추가하고 item을 정상 저장한다
6. IF `raw_s3_uri`를 결정할 수 없으면, THEN THE DynamoDB_Store SHALL `raw_s3_uri` 필드에 문자열 `unknown`을 저장하고 item 저장을 중단하지 않는다

### Requirement 2: 결정론적 관광지 Subtype 매핑

**User Story:** As a 데이터 엔지니어, I want `lclsSystm3` 코드를 기반으로 관광지 subtype을 결정론적으로 생성하고 싶다, so that 동일 입력에서 항상 동일한 subtype이 생성되고 LLM 호출 없이 분류가 가능하다.

#### Acceptance Criteria

1. WHEN `lcls_systm3` 코드가 `classification_dict.json`에 존재하고 해당 entry의 `type`이 `Attraction`이면, THE DynamoDB_Store SHALL `attraction_subtype_code`에 매핑 entry의 `code` 값을, `attraction_subtype_name`에 매핑 entry의 `name` 값을 저장한다
2. WHEN subtype 매핑이 성공하면, THE DynamoDB_Store SHALL `classification_source` 필드에 고정 문자열 `lcls_systm3`를, `classification_mapping_version` 필드에 배포된 매핑표의 ISO 날짜 형식(YYYY-MM-DD) 버전 문자열을 함께 기록한다
3. IF `lcls_systm3` 코드가 분류 사전에 존재하지 않거나 해당 entry의 `type`이 `Attraction`이 아니면, THEN THE DynamoDB_Store SHALL `attraction_subtype_code`, `attraction_subtype_name`, `classification_source`, `classification_mapping_version` 필드를 기록하지 않고 해당 item을 `classification_review` queue로 전송한다
4. WHEN 관광지의 subtype 매핑이 수행될 때, THE DynamoDB_Store SHALL 기존 수집 단계에서 배정된 `theme`과 `theme_tags` 값을 변경하지 않고 원래 값 그대로 유지한다
5. WHEN 동일한 `lcls_systm3` 코드를 가진 서로 다른 item에 대해 매핑이 수행될 때, THE DynamoDB_Store SHALL 항상 동일한 `attraction_subtype_code`와 `attraction_subtype_name` 결과를 생성한다

### Requirement 3: Bedrock 관광지 메타데이터 추출

**User Story:** As a 여행 추천 서비스, I want 관광지 DynamoDB item에서 Bedrock LLM을 사용하여 4개 의미 기반 메타데이터 필드를 추출하고 싶다, so that 사용자의 감성·경험·동행 기반 검색과 필터링이 가능하다.

#### Acceptance Criteria

1. THE Enrichment_Engine SHALL `entity_type`이 `attraction`인 item에 대해서만 Bedrock 호출을 수행하고, 그 외 `entity_type` 값을 가진 item은 처리하지 않는다
2. WHEN Bedrock 호출이 실행될 때, THE Enrichment_Engine SHALL DynamoDB item에서 `entity_type`, `content_id`, `title`, `description`, `theme`, `theme_tags`, `experience_guide`, `opening_hours`, `closed_days`, `parking`, `address` 필드만 프롬프트 입력으로 사용한다
3. THE Enrichment_Engine SHALL `PK`, `SK`, `source_key`, `raw_s3_uri`, `classification_source`, `classification_mapping_version`, `metadata_enrichment` 필드를 프롬프트에 포함하지 않는다
4. THE Enrichment_Engine SHALL 정확히 4개 출력 필드(`indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`)만 허용하고, 이외의 필드가 응답에 포함되면 검증 오류로 처리한다
5. WHEN `indoor_outdoor` 값이 반환될 때, THE Enrichment_Engine SHALL `indoor`, `outdoor`, `mixed`, `unknown` 중 하나인지 검증한다
6. WHEN `vibe_tags`가 반환될 때, THE Enrichment_Engine SHALL Canonical_Taxonomy에 정의된 태그만 허용하고 최대 5개로 제한한다
7. WHEN `experience_tags`가 반환될 때, THE Enrichment_Engine SHALL Canonical_Taxonomy에 정의된 태그만 허용하고 최대 3개로 제한한다
8. WHEN `companion_fit`이 반환될 때, THE Enrichment_Engine SHALL Canonical_Taxonomy에 정의된 값(`family`, `kids`, `couple`, `solo`, `pet`, `parents`, `seniors`)만 허용하고 최대 7개로 제한한다
9. IF Bedrock 응답에 Canonical_Taxonomy에 없는 태그가 포함되면, THEN THE Enrichment_Engine SHALL 해당 태그를 제거하고 유효한 태그만 저장한다
10. IF Bedrock 호출 시 네트워크 타임아웃 또는 서비스 오류가 발생하면, THEN THE Enrichment_Engine SHALL 최대 2회 재시도(지수 백오프)를 수행한다
11. THE Enrichment_Engine SHALL 프롬프트 입력 문자열을 최대 12,000자로 제한하고 초과분을 잘라낸다

### Requirement 4: Enrichment 실행 이력 관리

**User Story:** As a 운영 엔지니어, I want 각 관광지 item에 enrichment 실행 상태와 이력을 기록하고 싶다, so that 실패 추적, 재처리 판단, 중복 호출 방지가 가능하다.

#### Acceptance Criteria

1. WHEN Bedrock 호출이 성공하면, THE DynamoDB_Store SHALL `metadata_enrichment` 객체에 `status=succeeded`, `model_id`, `prompt_version`, `schema_version`, `generated_at`(ISO 8601 UTC), `input_hash`를 기록한다
2. WHEN Bedrock 호출이 실패하면, THE DynamoDB_Store SHALL `metadata_enrichment` 객체에 `status=failed`, `error_code`(카테고리: `model_error`, `timeout`, `throttling`, `validation_error` 중 하나), `failed_at`(ISO 8601 UTC)를 기록하고 원본 item의 기존 필드를 유지한다
3. IF Bedrock 응답에서 4개 출력 필드(`indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`) 모두 `unknown` 또는 빈 값으로 반환되면, THEN THE DynamoDB_Store SHALL `metadata_enrichment.status`를 `skipped`로 기록하고 파생 필드를 저장하지 않는다
4. IF 동일 item에 대해 `input_hash`, `prompt_version`, `model_id`가 모두 이전 성공(`status=succeeded`) 실행과 같으면, THEN THE Enrichment_Engine SHALL Bedrock 재호출을 생략하고 기존 결과를 유지한다
5. THE Enrichment_Engine SHALL `input_hash`를 `title`, `description`, `theme`, `theme_tags`, `experience_guide`, `opening_hours`, `closed_days`, `parking`, `address` 필드를 키 알파벳순 정렬 후 공백 제거·소문자 변환한 문자열의 SHA-256 해시로 계산한다
6. IF 이전 실행 `status`가 `failed` 또는 `skipped`이고 `input_hash`, `prompt_version`, `model_id` 중 하나라도 변경되면, THEN THE Enrichment_Engine SHALL 해당 item에 대해 Bedrock 재호출을 수행한다

### Requirement 5: Enrichment 실패 시 원본 보존

**User Story:** As a 데이터 엔지니어, I want Bedrock 호출 실패 시 관광지 원본 item이 손상되지 않도록 보장하고 싶다, so that 실패가 서비스 데이터 품질에 영향을 주지 않는다.

#### Acceptance Criteria

1. IF Bedrock 모델 호출이 실패하면, THEN THE DynamoDB_Store SHALL 관광지 item에 `metadata_enrichment` 객체만 갱신하고, 그 외 기존 필드에 대한 쓰기를 수행하지 않는다
2. IF Bedrock 응답의 schema 검증이 실패하면, THEN THE DynamoDB_Store SHALL 파생 메타데이터 필드(`indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`)를 저장하지 않고 `metadata_enrichment.status`를 `failed`로, `metadata_enrichment.error_code`에 검증 실패 원인을 나타내는 오류 코드를 기록한다
3. THE Enrichment_Engine SHALL 성공한 enrichment 결과가 `title`, `description`, `theme`, `theme_tags`, `experience_guide`, `opening_hours`, `closed_days`, `parking`, `address`, `entity_type`, `content_id`, `PK`, `SK`, `source_key`, `raw_s3_uri`, `classification_source`, `classification_mapping_version` 필드를 덮어쓰지 않도록 보장한다
4. IF Bedrock 호출 중 네트워크 타임아웃 또는 서비스 오류가 발생하면, THEN THE Enrichment_Engine SHALL 최대 2회 재시도한 뒤에도 실패하면 해당 item을 실패로 처리하고 다음 item의 처리를 계속한다

### Requirement 6: 축제 원천 분류 및 프로그램 보존

**User Story:** As a 데이터 엔지니어, I want 축제 item에 원천 분류 코드와 프로그램 정보를 보존하고 싶다, so that 재분류의 입력 근거와 감사 비교가 가능하다.

#### Acceptance Criteria

1. WHEN 축제 raw 데이터가 전처리될 때, THE DynamoDB_Store SHALL `source_subtype_name` 필드에 `classification_dict[lcls_systm3].name` 값을 저장한다
2. WHEN 축제 raw 데이터가 전처리될 때, THE DynamoDB_Store SHALL `source_theme` 필드에 `classification_dict[lcls_systm3].theme` 값을 저장한다
3. IF 축제의 `lcls_systm3`가 `classification_dict.json`에 존재하지 않으면, THEN THE DynamoDB_Store SHALL `source_subtype_name`과 `source_theme`을 null로 저장하고 해당 item을 `classification_review` queue에 추가한다
4. WHEN 축제 raw 데이터에 `intro.program`이 null이 아니고 빈 문자열이 아니면, THE DynamoDB_Store SHALL `program` 필드에 해당 값을 저장한다
5. WHEN 축제 raw 데이터에 `intro.subevent`가 null이 아니고 빈 문자열이 아니면, THE DynamoDB_Store SHALL `subevent` 필드에 해당 값을 저장한다

### Requirement 7: Bedrock 축제 6대 테마 재분류

**User Story:** As a 여행 추천 서비스, I want 축제의 실제 내용을 기반으로 Lovv 6대 테마를 재분류하고 싶다, so that `lclsSystm3` 코드의 광범위한 분류(예: 문화관광축제·문화예술축제·기타축제가 모두 예술·감성으로 매핑)를 개선하여 정확한 테마 기반 검색이 가능하다.

#### Acceptance Criteria

1. THE Theme_Classifier SHALL `entity_type`이 `festival`인 item에 대해서만 Bedrock 호출을 수행한다
2. WHEN Bedrock 호출이 실행될 때, THE Theme_Classifier SHALL DynamoDB item에서 `entity_type`, `content_id`, `title`, `description`, `program`, `subevent`, `venue`, `playtime`, `lcls_systm3`, `source_theme` 필드만 프롬프트 입력으로 사용한다
3. THE Theme_Classifier SHALL `PK`, `SK`, `phone`, `tel`, `source_key`, `raw_s3_uri`, `festival_theme_classification` 필드를 모델에 전달하지 않는다
4. WHEN 재분류가 성공하면, THE Theme_Classifier SHALL `primary_theme` 정확히 1개와 `theme_tags` 최소 1개 최대 3개를 반환한다
5. IF `primary_theme`이 `theme_tags`에 포함되지 않으면, THEN THE Theme_Classifier SHALL `primary_theme`을 `theme_tags` 첫 번째 위치에 자동 삽입하여 포함 관계를 보장한다
6. THE Theme_Classifier SHALL 출력 테마를 Lovv_6대_테마(바다·해안, 자연·트레킹, 미식·노포, 역사·전통, 예술·감성, 온천·휴양)로만 제한한다
7. IF Bedrock 응답에 Lovv_6대_테마에 없는 값이 포함되면, THEN THE Theme_Classifier SHALL 해당 값을 제거하고, 유효한 테마가 1개 이상 남으면 유효한 값만으로 결과를 구성하고, 유효한 테마가 0개이면 분류를 실패로 처리한다
8. WHEN 축제의 `program`과 `subevent`에 먹거리 부스만 언급되고 축제의 핵심 주제(`title`, `description`)가 음식·미식과 무관한 경우, THE Theme_Classifier SHALL 해당 축제를 `미식·노포`로 분류하지 않는다
9. WHEN 축제의 `program`과 `subevent`에 부대 공연만 언급되고 축제의 핵심 주제(`title`, `description`)가 공연·예술과 무관한 경우, THE Theme_Classifier SHALL 해당 축제를 `예술·감성`으로 분류하지 않는다
10. WHEN `venue`에 해안·해수욕장·바다 관련 지명이 없고 `title`·`description`에 바다 관련 키워드가 없으며 물놀이 활동만 존재하는 경우, THE Theme_Classifier SHALL 해당 축제를 `바다·해안`이 아닌 `온천·휴양`으로 분류한다
11. WHEN 재분류가 성공하면, THE DynamoDB_Store SHALL `theme`에 `primary_theme`을, `theme_tags`에 검증된 다중 라벨을 저장하되, 원천 분류(`lcls_systm3`, `source_subtype_name`, `source_theme`)를 삭제하거나 덮어쓰지 않는다
12. IF 축제 item의 `title`, `description`, `program`, `subevent`가 모두 비어있거나 null이면, THEN THE Theme_Classifier SHALL Bedrock 호출을 생략하고 해당 item을 `festival_theme_review` queue에 추가한다

### Requirement 8: 축제 재분류 실행 이력 및 실패 정책

**User Story:** As a 운영 엔지니어, I want 축제 재분류 실행 이력을 관리하고 실패 시 안전한 처리를 보장하고 싶다, so that 잘못된 자동 승격 없이 품질을 유지할 수 있다.

#### Acceptance Criteria

1. WHEN 재분류가 성공하면, THE DynamoDB_Store SHALL `festival_theme_classification` 객체에 `status=succeeded`, `model_id`, `prompt_version`, `schema_version`, `generated_at`, `input_hash`를 기록한다
2. IF Bedrock 응답에서 `primary_theme` 또는 `theme_tags` 근거로 사용할 입력 필드(`description`, `program`, `subevent`) 중 유효한 텍스트가 모두 비어있거나 30자 미만이면, THEN THE DynamoDB_Store SHALL `festival_theme_classification.status`를 `review_required`로 기록하고 해당 item을 `festival_theme_review` queue에 추가한다
3. IF Bedrock 모델 호출 또는 schema 검증이 실패하면, THEN THE Theme_Classifier SHALL `source_theme`을 최종 `theme`으로 자동 승격하지 않고, 기존 `theme` 및 `theme_tags` 필드 값을 변경 없이 유지하며, `festival_theme_classification.status`를 `failed`로, `error_code`를 실패 원인 식별 코드로 기록한다
4. WHEN 동일 item에 대해 `input_hash`, `prompt_version`, `model_id`가 모두 이전 실행과 같고 이전 실행의 `festival_theme_classification.status`가 `succeeded`이면, THE Theme_Classifier SHALL Bedrock 재호출을 생략하고 기존 성공 결과를 유지한다
5. THE Theme_Classifier SHALL `festival_theme_classification.status`가 `succeeded`인 축제만 festival month/theme seed 검색에 사용하도록 보장한다
6. THE Theme_Classifier SHALL `input_hash`를 Requirement 7 Criterion 2에 정의된 프롬프트 입력 필드(`entity_type`, `content_id`, `title`, `description`, `program`, `subevent`, `venue`, `playtime`, `lcls_systm3`, `source_theme`)의 정규화된 SHA-256 해시로 계산한다

### Requirement 9: S3 Vector Metadata 확장

**User Story:** As a 검색 서비스, I want enrichment로 생성된 필드를 S3 Vector의 filterable metadata에 추가하고 싶다, so that 사용자가 감성·경험·동행 기반으로 관광지를 필터링할 수 있다.

#### Acceptance Criteria

1. WHEN `entity_type`이 `attraction`인 item의 vector metadata를 구성할 때, THE Vector_Metadata_Builder SHALL filterable metadata allowlist에 `attraction_subtype_code`, `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `schema_version`을 추가한다
2. THE Vector_Metadata_Builder SHALL filterable metadata의 UTF-8 인코딩 크기가 2048 bytes를 초과하지 않도록 검증한다
3. THE Vector_Metadata_Builder SHALL `None`, 빈 문자열, 빈 배열 값을 metadata에 포함하지 않는다
4. THE Vector_Metadata_Builder SHALL `description`, `overview`, embedding 입력 원문, `opening_hours`, `closed_days`, `experience_guide`, `parking`, `homepage`, `image_url`을 vector metadata에 포함하지 않는다
5. THE Vector_Metadata_Builder SHALL `metadata_enrichment` 전체 객체를 vector metadata에 포함하지 않는다
6. IF filterable metadata의 UTF-8 인코딩 크기가 2048 bytes를 초과하면, THEN THE Vector_Metadata_Builder SHALL 배열 필드(`vibe_tags`, `experience_tags`)의 항목을 뒤에서부터 제거하여 2048 bytes 이내로 축소하고, 축소 후에도 초과하면 해당 item을 오류로 기록하고 metadata 생성을 중단한다
7. WHEN vector metadata를 구성할 때, THE Vector_Metadata_Builder SHALL DynamoDB item의 `metadata_enrichment.status`가 `succeeded`인 경우에만 enrichment 파생 필드를 포함한다

### Requirement 10: 축제 월별 조회를 위한 GSI 보완

**User Story:** As a 여행 추천 서비스, I want 축제를 월(month) 기반으로 효율적으로 조회하고 싶다, so that 특정 월에 열리는 축제를 테마와 함께 빠르게 검색할 수 있다.

#### Acceptance Criteria

1. THE DynamoDB_Store SHALL 축제 item의 GSI Sort Key에 월(month) 정보를 포함하여 월별 range query를 지원한다
2. WHEN 축제 item이 저장될 때, THE DynamoDB_Store SHALL GSI SK를 `FESTIVAL#{month:02d}#{content_id}` 형식(예: `FESTIVAL#10#2002`)으로 구성하여 월별 정렬과 prefix 조회가 가능하도록 한다
3. THE DynamoDB_Store SHALL 기존 테이블의 PK(`CITY#{city_name_en}`)와 SK(`FESTIVAL#{content_id}`) 구조를 변경하지 않고, 별도 GSI를 통해 월별 조회를 지원한다
4. WHEN GSI를 통해 축제를 조회할 때, THE DynamoDB_Store SHALL `entity_type=festival`과 월(month)을 조합한 KeyConditionExpression으로 해당 월에 열리는 축제 목록을 반환한다
5. IF 축제의 `event_start_date`가 없어 month를 결정할 수 없으면, THEN THE DynamoDB_Store SHALL 해당 축제의 GSI SK에 month 대신 `00`을 사용하고 item을 정상 저장한다
6. WHEN 축제가 여러 달에 걸쳐 진행되는 경우(visit_months가 2개 이상), THE DynamoDB_Store SHALL 시작 월(event_start_date 기준)을 GSI SK의 month 값으로 사용한다
7. THE DynamoDB_Store SHALL 재분류가 성공한 축제(`festival_theme_classification.status=succeeded`)만 theme 기반 seed 검색에 노출하고, GSI 조회 결과에서 `festival_theme_classification.status`로 필터링할 수 있도록 해당 필드를 GSI에 프로젝션한다

### Requirement 11: 파이프라인 단계 분리

**User Story:** As a 시스템 아키텍트, I want 관광지 enrichment와 축제 재분류를 별도 실행 단계로 분리하고 싶다, so that 재색인 시 불필요한 Bedrock 재호출을 방지하고 각 단계를 독립적으로 배포·검증할 수 있다.

#### Acceptance Criteria

#### Acceptance Criteria

1. THE Enrichment_Engine SHALL 관광지 전용 독립 모듈로 구성되어 Theme_Classifier 또는 Vector_Metadata_Builder 실행 없이 단독으로 호출 가능하다
2. THE Theme_Classifier SHALL 축제 전용 독립 모듈로 구성되어 Enrichment_Engine 또는 Vector_Metadata_Builder 실행 없이 단독으로 호출 가능하다
3. WHEN vector index가 재빌드될 때, THE Vector_Metadata_Builder SHALL DynamoDB에서 `metadata_enrichment.status`가 `succeeded`인 item의 enrichment 결과만 읽고 Bedrock을 직접 호출하지 않는다
4. WHILE 단일 실행에서 처리 대상 item이 500건을 초과하면, THE Enrichment_Engine SHALL 도시 코드 또는 최대 100건 단위의 고정 batch로 분할하여 순차 실행한다
5. IF batch 실행 중 일부 item이 실패하면, THEN THE Enrichment_Engine SHALL 실패한 item을 건너뛰고 나머지 batch를 계속 처리하며, 실패 item의 `content_id`와 오류 코드를 실행 로그에 기록한다
