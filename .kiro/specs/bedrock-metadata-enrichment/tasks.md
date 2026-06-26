# Implementation Plan: Bedrock Metadata Enrichment

## Overview

본 구현 계획은 (1) 식당(restaurant) entity 지원 제거, (2) 전처리 단계에 원천 분류 코드 보존 및 결정론적 subtype 매핑 추가, (3) Bedrock 관광지 메타데이터 추출 모듈 구현, (4) Bedrock 축제 테마 재분류 모듈 구현, (5) Vector metadata 확장, (6) 축제 월별 GSI 지원의 순서로 진행한다.

식당 제거를 가장 먼저 수행하여 이후 enrichment 작업이 단순화된 파이프라인 위에서 진행되도록 한다.

## Tasks

- [x] 1. Remove restaurant entity support from the pipeline
  - [x] 1.1 Remove restaurant handling from `domain_preprocess.py`
    - Remove `"restaurant"` key from `DOMAIN_KEYS` dict
    - In `_classify_domain()`, change `contenttypeid == "39"` to return `"excluded"` instead of `"restaurant"`
    - Remove the `if entity_type == "restaurant":` branch in `_build_domain_item()`
    - Remove `"restaurants"` bucket from `preprocess_city_payload()` and related summary count
    - Remove `_write_jsonl(normalized_dir / "restaurants.jsonl", ...)` from `write_preprocess_output()`
    - _Requirements: Pipeline simplification (user request)_

  - [x] 1.2 Remove restaurant from `kr_vector_index/export.py`
    - Remove `"restaurant"` from `VECTORIZABLE_ENTITY_TYPES` tuple
    - _Requirements: Pipeline simplification (user request)_

  - [x] 1.3 Remove restaurant-specific logic from `kr_vector_index/chunks.py`
    - Remove restaurant-specific branch in `build_embedding_text()` (음식 카테고리, 대표메뉴, 운영시간, 휴무)
    - Remove `"음식점"` from `_type_label()` mapping
    - Remove restaurant-specific category handling in `_tags()`
    - _Requirements: Pipeline simplification (user request)_

  - [x] 1.4 Update tests for restaurant removal
    - Update `test_domain_preprocess.py`: change contenttypeid "39" test data to expect `"excluded"` entity_type, remove restaurant-specific assertions, adjust summary counts
    - Update `test_chunks.py`: remove `test_restaurant_chunk_includes_dynamodb_address` or convert to excluded/review test
    - Update `test_export.py`: remove restaurant from `should_vectorize` test cases
    - Update `test_vector_index_handler.py`: remove restaurant entity references from mock data and assertions
    - Update `test_upsert.py`: change restaurant references to attraction or festival in test fixtures
    - Update `test_metadata.py`: change restaurant entity_type to attraction in test fixtures
    - _Requirements: Pipeline simplification (user request)_

- [x] 2. Checkpoint - Restaurant removal verification
  - Ensure all tests pass after restaurant removal, ask the user if questions arise.

- [x] 3. Extend preprocessing with source classification preservation
  - [x] 3.1 Implement `extract_lcls_systm3()` in `domain_preprocess.py`
    - Add function to extract `common.lclsSystm3` with fallback to record top-level `lclsSystm3`
    - Return `None` when both sources are absent
    - Add `lcls_systm3`, `source_type`, `raw_s3_uri` to `COMMON_KEYS` set
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 3.2 Create `classification_dict.json` and implement `map_attraction_subtype()`
    - Create `src/kr_details_pipeline/classification_dict.json` with lcls_systm3 code-to-subtype mappings
    - Implement `map_attraction_subtype()` function that performs deterministic lookup
    - Return `SubtypeMappingResult` with code, name, source, and version fields
    - Handle unmapped codes by adding to `classification_review` queue
    - Add `attraction_subtype_code`, `attraction_subtype_name`, `classification_source`, `classification_mapping_version` to attraction `DOMAIN_KEYS`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.3 Implement `preserve_festival_source()` and update festival preprocessing
    - Implement `preserve_festival_source()` to extract `source_subtype_name`, `source_theme`, `program`, `subevent` from classification_dict and intro fields
    - Integrate into `_build_domain_item()` festival branch
    - Add `source_subtype_name`, `source_theme`, `program`, `subevent`, `theme`, `theme_tags` to festival `DOMAIN_KEYS`
    - Handle missing lcls_systm3 by sending to `classification_review` queue
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 3.4 Integrate source fields into `_build_domain_item()`
    - Call `extract_lcls_systm3()` for both attraction and festival branches
    - Set `source_type = "tourapi"` constant
    - Set `raw_s3_uri` from source_key or `"unknown"` fallback
    - Call `map_attraction_subtype()` in attraction branch
    - Call `preserve_festival_source()` in festival branch
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3_

  - [ ]* 3.5 Write property tests for lcls_systm3 extraction (Property 1)
    - **Property 1: lcls_systm3 추출 및 폴백**
    - Test `common.lclsSystm3` priority over record top-level
    - Test fallback to record top-level when common is absent
    - Test None return when both are absent
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 3.6 Write property tests for subtype mapping (Property 2, 3)
    - **Property 2: 결정론적 subtype 매핑**
    - **Property 3: 미매핑 코드의 review queue 전송과 theme 보존**
    - Test deterministic mapping consistency across multiple calls
    - Test unmapped codes route to classification_review queue
    - Test theme/theme_tags preservation on unmapped codes
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

  - [ ]* 3.7 Write property test for festival source preservation (Property 8)
    - **Property 8: 축제 원천 분류 및 프로그램 보존**
    - Test source_subtype_name and source_theme from classification_dict
    - Test program and subevent preservation from intro fields
    - **Validates: Requirements 6.1, 6.2, 6.4, 6.5**

- [x] 4. Checkpoint - Preprocessing extension verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Bedrock attraction enrichment engine
  - [x] 5.1 Create `src/kr_details_pipeline/enrichment_engine.py` with core interfaces
    - Define `EnrichmentResult` dataclass
    - Define `BatchResult` dataclass
    - Implement `compute_input_hash()` for attraction items (SHA-256 of sorted, normalized fields)
    - Implement `should_skip_enrichment()` for input_hash-based deduplication
    - Define canonical taxonomy constants (VIBE_TAGS, EXPERIENCE_TAGS, COMPANION_FIT, INDOOR_OUTDOOR)
    - _Requirements: 4.4, 4.5, 4.6_

  - [x] 5.2 Implement `build_extraction_prompt()` for attraction items
    - Build prompt string from allowed fields only (entity_type, content_id, title, description, theme, theme_tags, experience_guide, opening_hours, closed_days, parking, address)
    - Exclude forbidden fields (PK, SK, source_key, raw_s3_uri, classification_source, classification_mapping_version, metadata_enrichment)
    - Enforce 12,000 character limit with truncation
    - _Requirements: 3.2, 3.3, 3.11_

  - [x] 5.3 Implement `validate_extracted_metadata()` for Bedrock response validation
    - Validate only 4 output fields allowed (indoor_outdoor, vibe_tags, experience_tags, companion_fit)
    - Validate indoor_outdoor against {indoor, outdoor, mixed, unknown}
    - Filter vibe_tags against canonical taxonomy, max 5
    - Filter experience_tags against canonical taxonomy, max 3
    - Filter companion_fit against canonical values, max 7
    - Remove non-canonical tags silently
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x] 5.4 Implement `enrich_attraction()` with Bedrock converse API call
    - Filter for entity_type="attraction" only
    - Call Bedrock converse API with retry logic (max 2 retries, exponential backoff)
    - Parse JSON response and validate
    - Handle all-unknown/empty output as "skipped" status
    - Build metadata_enrichment history object on success/failure
    - _Requirements: 3.1, 3.10, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_

  - [x] 5.5 Implement `run_enrichment_batch()` for batch processing
    - Split items into max 100-item batches when total exceeds 500
    - Process each item, skip failures, continue with remaining
    - Log failed item content_ids and error codes
    - Return BatchResult with success/failure/skip counts
    - _Requirements: 11.1, 11.4, 11.5_

  - [ ]* 5.6 Write property test for prompt field boundary (Property 4)
    - **Property 4: 관광지 프롬프트 필드 경계**
    - Generate random attraction items with both allowed and forbidden fields
    - Assert prompt contains only allowed field values
    - Assert prompt never contains forbidden field values
    - Assert prompt length ≤ 12,000 characters
    - **Validates: Requirements 3.2, 3.3, 3.11**

  - [ ]* 5.7 Write property test for canonical taxonomy validation (Property 5)
    - **Property 5: Canonical Taxonomy 검증**
    - Generate random Bedrock responses with valid and invalid tags
    - Assert invalid tags removed, valid tags preserved
    - Assert max cardinality enforced per field
    - Assert indoor_outdoor validated against allowed set
    - **Validates: Requirements 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**

  - [ ]* 5.8 Write property test for input_hash deduplication (Property 6)
    - **Property 6: input_hash 기반 중복 호출 방지**
    - Assert same input_hash + prompt_version + model_id with succeeded status → skip
    - Assert changed hash or failed status → re-invoke
    - **Validates: Requirements 4.4, 4.5, 4.6**

  - [ ]* 5.9 Write property test for failure preservation (Property 7)
    - **Property 7: 실패 시 원본 item 보존 불변식**
    - Assert on failure: only metadata_enrichment updated
    - Assert derived fields not stored on failure
    - Assert source fields never overwritten on success
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ]* 5.10 Write property test for batch processing (Property 14)
    - **Property 14: 배치 분할과 장애 격리**
    - Assert 500+ items split into max 100-item batches
    - Assert individual item failures don't halt batch
    - **Validates: Requirements 11.4, 11.5**

- [x] 6. Checkpoint - Enrichment engine verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Bedrock festival theme classifier
  - [x] 7.1 Create `src/kr_details_pipeline/theme_classifier.py` with core interfaces
    - Define `ThemeClassificationResult` dataclass
    - Define Lovv 6대 테마 constants
    - Implement `compute_festival_input_hash()` (SHA-256 of sorted, normalized festival fields)
    - Implement `should_skip_classification()` for input_hash-based deduplication
    - _Requirements: 8.4, 8.6_

  - [x] 7.2 Implement `build_festival_prompt()` for festival items
    - Build prompt from allowed fields (entity_type, content_id, title, description, program, subevent, venue, playtime, lcls_systm3, source_theme)
    - Exclude forbidden fields (PK, SK, phone, tel, source_key, raw_s3_uri, festival_theme_classification)
    - _Requirements: 7.2, 7.3_

  - [x] 7.3 Implement `validate_festival_theme_output()` for Bedrock response validation
    - Validate primary_theme is exactly 1 valid 6대 테마
    - Validate theme_tags has 1-3 valid 6대 테마
    - Auto-insert primary_theme into theme_tags[0] if missing
    - Remove invalid themes; fail if 0 valid themes remain
    - _Requirements: 7.4, 7.5, 7.6, 7.7_

  - [x] 7.4 Implement `classify_festival_theme()` with Bedrock call
    - Filter for entity_type="festival" only
    - Skip items with insufficient text (all text fields < 30 chars) → status=review_required
    - Call Bedrock converse API with retry logic
    - On success: update theme and theme_tags, preserve source fields
    - On failure: preserve existing theme/theme_tags, no auto-promotion of source_theme
    - Build festival_theme_classification history object
    - _Requirements: 7.1, 7.8, 7.9, 7.10, 7.11, 7.12, 8.1, 8.2, 8.3, 8.5_

  - [x] 7.5 Implement `run_classification_batch()` for batch processing
    - Split items into max 100-item batches when total exceeds 500
    - Process each item, skip failures, continue with remaining
    - Return BatchResult with success/failure/review_required counts
    - _Requirements: 11.2_

  - [ ]* 7.6 Write property test for festival prompt field boundary (Property 9)
    - **Property 9: 축제 프롬프트 필드 경계**
    - Generate random festival items with allowed and forbidden fields
    - Assert prompt contains only allowed field values
    - Assert prompt never contains forbidden field values
    - **Validates: Requirements 7.2, 7.3**

  - [ ]* 7.7 Write property test for festival theme output validation (Property 10)
    - **Property 10: 축제 테마 출력 검증**
    - Generate random Bedrock responses with valid/invalid themes
    - Assert primary_theme is valid 6대 테마
    - Assert theme_tags 1-3 valid themes
    - Assert primary_theme auto-inserted into theme_tags
    - Assert 0 valid themes → failure
    - **Validates: Requirements 7.4, 7.5, 7.6, 7.7**

  - [ ]* 7.8 Write property test for source classification preservation (Property 11)
    - **Property 11: 축제 재분류 시 원천 분류 보존**
    - Assert on success: theme/theme_tags updated, source fields preserved
    - Assert on failure: theme/theme_tags unchanged, no auto-promotion
    - **Validates: Requirements 7.11, 8.3**

- [x] 8. Checkpoint - Theme classifier verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Extend vector metadata builder
  - [x] 9.1 Update `src/kr_vector_index/metadata.py` with enrichment fields
    - Add `attraction_subtype_code`, `indoor_outdoor`, `vibe_tags`, `experience_tags`, `companion_fit`, `schema_version` to `FILTERABLE_METADATA_KEYS`
    - Add `description`, `overview`, `opening_hours`, `closed_days`, `experience_guide`, `parking`, `homepage`, `image_url`, `metadata_enrichment` to a `FORBIDDEN_METADATA_KEYS` set
    - _Requirements: 9.1, 9.4, 9.5_

  - [x] 9.2 Implement `build_enriched_metadata()` in `metadata.py`
    - Only include enrichment derived fields when `metadata_enrichment.status == "succeeded"`
    - Strip None, empty string, and empty array values
    - Enforce forbidden fields exclusion
    - _Requirements: 9.3, 9.7_

  - [x] 9.3 Implement `trim_to_budget()` in `metadata.py`
    - Check UTF-8 encoded size against 2048 bytes budget
    - If exceeded, trim array fields (vibe_tags, experience_tags) from the end
    - If still exceeded after trimming, return None and log error
    - _Requirements: 9.2, 9.6_

  - [x] 9.4 Update `build_chunk()` in `chunks.py` to use enriched metadata
    - Integrate `build_enriched_metadata()` call for attraction items
    - Include festival theme fields (primary_theme, theme_tags) for festivals with succeeded status
    - Remove restaurant references from `_type_label()` if any remain
    - _Requirements: 9.1, 9.7, 11.3_

  - [ ]* 9.5 Write property test for vector metadata contract (Property 12)
    - **Property 12: Vector metadata 계약**
    - Generate random items with varying metadata_enrichment.status
    - Assert non-succeeded items exclude enrichment fields
    - Assert None/empty values excluded
    - Assert forbidden fields never present
    - Assert UTF-8 size ≤ 2048 bytes after trim
    - **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 9.6, 9.7**

- [x] 10. Implement festival monthly GSI support
  - [x] 10.1 Add GSI SK generation for festival items
    - Implement `build_festival_gsi_sk()` function: `FESTIVAL#{month:02d}#{content_id}`
    - Use `event_start_date` month; default to `00` when missing
    - For multi-month festivals, use start month only
    - Integrate GSI SK into festival item preprocessing
    - _Requirements: 10.1, 10.2, 10.5, 10.6_

  - [x] 10.2 Add GSI query helper for monthly festival lookup
    - Implement query function using `entity_type=festival` + month prefix on GSI SK
    - Project `festival_theme_classification.status` for filtering
    - Preserve existing PK/SK structure unchanged
    - _Requirements: 10.3, 10.4, 10.7_

  - [ ]* 10.3 Write property test for GSI SK format (Property 13)
    - **Property 13: GSI SK 형식과 월 결정**
    - Generate random festival items with/without event_start_date
    - Assert SK format matches `FESTIVAL#{month:02d}#{content_id}`
    - Assert missing date → month=00
    - Assert multi-month festivals use start month
    - **Validates: Requirements 10.2, 10.5, 10.6**

- [x] 11. Final checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Task 1 (restaurant removal) is a prerequisite for all enrichment work — it simplifies the pipeline
- Checkpoints ensure incremental validation at each major phase
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python, matching the existing codebase
- All Bedrock integration uses mock clients in tests (no live API calls in test suite)
- `hypothesis` library is used for property-based tests
- `moto` library is used for DynamoDB/S3 integration tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4"] },
    { "id": 4, "tasks": ["3.5", "3.6", "3.7"] },
    { "id": 5, "tasks": ["5.1", "7.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "7.2", "7.3"] },
    { "id": 7, "tasks": ["5.4", "5.5", "7.4", "7.5"] },
    { "id": 8, "tasks": ["5.6", "5.7", "5.8", "5.9", "5.10", "7.6", "7.7", "7.8"] },
    { "id": 9, "tasks": ["9.1"] },
    { "id": 10, "tasks": ["9.2", "9.3", "10.1"] },
    { "id": 11, "tasks": ["9.4", "9.5", "10.2"] },
    { "id": 12, "tasks": ["10.3"] }
  ]
}
```
