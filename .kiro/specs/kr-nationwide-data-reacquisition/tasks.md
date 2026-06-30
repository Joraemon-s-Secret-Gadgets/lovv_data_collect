# Implementation Plan: KR Nationwide Data Reacquisition

## Overview

Extend the South Korea city data acquisition pipeline from limited scope (강원·경북 only) to nationwide coverage of all ~226 municipalities across all 17 provinces. The implementation adds CLI enhancements, province-aware batch processing, a DataLab visitor statistics collector with signguCode mapping, a merge pipeline, and robustness features (key rotation, retry, incremental persistence).

This plan also contains the merged TourAPI unique city key reacquisition bugfix work. The former standalone bugfix Spec is no longer the active planning surface; its requirements are represented here as Task 12.

## Tasks

- [ ] 1. Extend CLI and province-level batch execution
  - [x] 1.1 Add PROVINCE_TARGET_MAP and new CLI arguments to `city_wikipedia_acquisition.py`
    - Add `PROVINCE_TARGET_MAP` dictionary mapping all 17 province ISO codes (KR-11 through KR-50) to their corresponding target file names
    - Add `--province-id <KR-XX>` argument to process a single province
    - Add `--all-provinces` flag to process all 17 provinces sequentially
    - Add `--force-refresh` flag (passed through to DataLab collector)
    - Implement resolution logic: when `--province-id` is specified, resolve target file path from PROVINCE_TARGET_MAP and set `default_prefecture_id`
    - When `--all-provinces` is specified, iterate all entries in PROVINCE_TARGET_MAP in sequence, calling `acquire_city_data` for each
    - Validate mutual exclusivity: `--province-id` and `--all-provinces` cannot be combined with `--input`
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 1.2 Write unit tests for CLI argument parsing and province resolution
    - Test `--province-id KR-11` resolves to `seoul_municipalities_ko.json`
    - Test `--all-provinces` iterates all 17 province files
    - Test mutual exclusivity validation
    - Test `--force-refresh` flag is passed correctly
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 2. Implement province-aware batch processing in pipeline
  - [x] 2.1 Add `ProvinceResult` dataclass and `acquire_province` function to `pipeline.py`
    - Add `ProvinceResult` dataclass with fields: `province_id`, `newly_acquired`, `skipped`, `failed`, `failed_titles`
    - Implement `acquire_province(province_id, output_dir, client)` that resolves target file, calls `acquire_city_data` with correct `default_prefecture_id`, and returns `ProvinceResult`
    - Implement failure isolation: catch exceptions per municipality, log, continue with remaining, persist successful records before returning
    - _Requirements: 2.2, 2.4, 2.5, 9.1, 9.3_

  - [x] 2.2 Add `acquire_all_provinces` function to `pipeline.py`
    - Implement `acquire_all_provinces(output_dir, client)` that iterates all 17 provinces, logs progress per province, and returns a list of `ProvinceResult`
    - Ensure incremental merge: each province's newly acquired CityRecords merge into existing `cities.json` without overwriting records from other provinces
    - Log collection summary: total newly_acquired, skipped, failed across all provinces
    - _Requirements: 2.3, 2.4, 9.1, 9.3_

  - [ ]* 2.3 Write property test for incremental merge preservation (Property 1)
    - **Property 1: Incremental Merge Preserves Existing Records**
    - Generate random existing CityRecord sets and new CityRecord sets, verify merge preserves all previously collected records from other provinces (keyed by city_id)
    - **Validates: Requirements 2.4, 8.1, 9.1**

  - [ ]* 2.4 Write property test for failure persistence (Property 2)
    - **Property 2: Failure Persistence Guarantee**
    - Simulate failure at position N in a sequence of municipality fetches, verify all CityRecords at positions 0..N-1 are persisted to disk
    - **Validates: Requirements 2.5, 9.4**

  - [ ]* 2.5 Write property test for province-level progress accounting (Property 13)
    - **Property 13: Province-Level Progress Accounting**
    - Generate province runs with T total targets and outcomes (acquired/skipped/failed), verify `newly_acquired + skipped + failed == T`
    - **Validates: Requirements 9.3**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Validate target file coverage and MUNICIPALITY_EN_MAP completeness
  - [x] 4.1 Add `validate_target_coverage` function to `provinces.py`
    - Implement `validate_target_coverage(targets_dir: Path) -> list[str]` that returns municipality names from MUNICIPALITY_EN_MAP not found in any target file
    - Load all 17 target files from `crawling/KR/targets/`, collect all titles, and compare against MUNICIPALITY_EN_MAP keys
    - Log discrepancies if any municipalities are missing from target files
    - _Requirements: 1.1, 1.3_

  - [ ]* 4.2 Write property test for target file province association (Property 3)
    - **Property 3: Target File Province Association**
    - For target files loaded with a given province prefix_id, verify every PageTarget has its `prefecture_id` field set to that province's ID
    - **Validates: Requirements 1.2, 1.4**

  - [ ]* 4.3 Write property test for MUNICIPALITY_EN_MAP format invariants (Property 4)
    - **Property 4: MUNICIPALITY_EN_MAP Format Invariants**
    - Iterate all MUNICIPALITY_EN_MAP entries; verify values are uppercase ASCII `[A-Z][A-Z0-9-]*`, disambiguated entries have parentheses suffix, and city_id generation is `"{prefecture_id}-{en_name}"`
    - **Validates: Requirements 3.2, 3.3, 3.4**

- [ ] 5. Implement DataLab collector module with signguCode mapping
  - [x] 5.1 Create `crawling/KR/signgu_codes.json` with nationwide signguCode mapping
    - Create the JSON mapping file with entries for all municipalities: each entry keyed by numeric signguCode containing `city_name_ko`, `city_name_en`, and `province_id`
    - Ensure consistent code length (10 digits as per Korean standard administrative codes)
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 Create `crawling/KR/datalab_collector.py` with core data models and `BigDataClient`
    - Define `SignguCodeEntry` dataclass (code, city_name_ko, city_name_en, province_id)
    - Define `MonthlyVisitorData` and `VisitorStatistics` dataclasses
    - Implement `SignguCodeMapping` class to load and validate `signgu_codes.json`
    - Implement `BigDataClient` class with API key rotation: load keys from environment, rotate on HTTP 429 / code 22/0022, raise RuntimeError when all keys exhausted
    - Implement minimum delay between consecutive API requests
    - Implement retry with exponential backoff (3 retries: 2s, 4s, 8s) for transient network errors
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 5.3 Implement `collect_visitor_statistics` orchestrator in `datalab_collector.py`
    - Implement `collect_visitor_statistics(year, mapping, client, output_path, force_refresh)` — main collection loop
    - Iterate 12 months, query `locgoRegnVisitrDDList` endpoint per month
    - Filter API response items by signguCode against the nationwide mapping
    - Implement resumability: check if municipality already has complete 12-month data, skip unless `--force-refresh`
    - Persist results incrementally to `data/visitor/monthly_visitor_averages.json`
    - _Requirements: 6.1, 6.2, 9.2_

  - [x] 5.4 Implement `aggregate_monthly` pure function in `datalab_collector.py`
    - Implement daily→monthly aggregation: sum `touNum` values grouped by `touDivCd` (1=locals, 2=out_of_town, 3=foreigners)
    - Compute daily averages: `monthly_total / days_in_month` rounded to 2 decimal places
    - Compute annual totals and annual daily averages
    - Output `VisitorStatistics` with `annual_totals`, `annual_daily_averages`, `monthly_statistics` arrays
    - _Requirements: 6.3, 6.4, 6.5_

  - [ ]* 5.5 Write property test for signguCode mapping validity (Property 5)
    - **Property 5: signguCode Mapping Validity**
    - Iterate all signguCode entries, verify code is numeric string ≥5 digits and both `city_name_ko`/`city_name_en` are non-empty
    - **Validates: Requirements 5.2, 5.3**

  - [ ]* 5.6 Write property test for visitor statistics aggregation (Property 6)
    - **Property 6: Visitor Statistics Aggregation Correctness**
    - Generate random daily visitor records, verify monthly total equals sum of touNum by touDivCd, and daily average equals `total / days_in_month` (rounded to 2dp)
    - **Validates: Requirements 6.3, 6.4**

  - [ ]* 5.7 Write property test for signguCode filtering (Property 9)
    - **Property 9: signguCode Filtering in API Response Processing**
    - Generate API response items with mixed signguCodes (some in mapping, some not), verify only mapped codes are included in aggregation results
    - **Validates: Requirements 6.2**

  - [ ]* 5.8 Write property test for API key rotation (Property 10)
    - **Property 10: API Key Rotation on Quota Exhaustion**
    - Generate quota error sequences, verify client advances to next key and retries; verify key index never exceeds pool size
    - **Validates: Requirements 7.1**

  - [ ]* 5.9 Write property test for resumable DataLab collection (Property 14)
    - **Property 14: Resumable DataLab Collection**
    - Generate municipalities with/without existing complete data, verify collector skips already-complete municipalities unless `--force-refresh`
    - **Validates: Requirements 9.2**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement merge pipeline
  - [x] 7.1 Create `crawling/KR/merge_pipeline.py` with merge logic
    - Implement `MergeResult` dataclass to track merge outcomes (merged_count, wikipedia_only_count, visitor_only_count, total)
    - Implement `merge_city_with_visitor_stats(cities_path, visitor_stats_path, output_dir)` function
    - For cities with both sources: embed `visitor_statistics` into city's final output
    - For cities with only Wikipedia metadata: mark `visitor_statistics` as incomplete
    - For cities with only visitor stats: mark metadata as incomplete
    - Output per-city JSON files to `data/KR/final/{CITY_EN}.json`
    - _Requirements: 8.1, 8.3, 8.4, 8.5_

  - [ ]* 7.2 Write property test for merge strategy (Property 8)
    - **Property 8: Merge Strategy Preserves Available Data**
    - Generate cities with partial data sources (Wikipedia only, visitor only, both), verify merged output contains all available data and marks missing sources as incomplete
    - **Validates: Requirements 8.3, 8.5**

  - [ ]* 7.3 Write property test for field status and confidence (Property 7)
    - **Property 7: Field Status and Confidence Consistency**
    - Generate CityRecords with varying field presence, verify `field_status` has entries for all core fields, and `data_confidence` is "medium"/"high" when lat/long are non-null and prefecture_id is non-empty
    - **Validates: Requirements 4.4, 4.5**

- [ ] 8. Verify S3 upload handles nationwide dataset
  - [x] 8.1 Validate existing S3 uploader handles larger file sizes and add integration wiring
    - Verify `s3_uploader.py` handles the larger nationwide dataset (~226 cities vs 18) without timeout — existing implementation streams body via `put_object` so no changes needed
    - Wire the `--upload-to-s3` path in CLI to work with the new `--all-provinces` workflow
    - Ensure S3 key pattern remains `raw/KR/wikipedia/{YYYYMMDD}/{filename}`
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 8.2 Write property test for checksum deduplication (Property 11)
    - **Property 11: Checksum-Based Upload Deduplication**
    - Generate file content pairs with matching/mismatching checksums, verify upload is skipped when checksums match and proceeds when they differ
    - **Validates: Requirements 10.2**

  - [ ]* 8.3 Write property test for S3 key pattern format (Property 12)
    - **Property 12: S3 Key Pattern Format**
    - Generate date strings in YYYYMMDD format, verify generated S3 key matches `raw/KR/wikipedia/{YYYYMMDD}/{filename}`
    - **Validates: Requirements 10.4**

- [ ] 9. Final integration and wiring
  - [x] 9.1 Wire all components together in CLI and add end-to-end smoke validation
    - Integrate `datalab_collector.py` invocation from CLI (new `--collect-visitor-stats` flag or separate command)
    - Integrate `merge_pipeline.py` invocation from CLI (new `--merge` flag or separate command)
    - Ensure the full flow works: province acquisition → DataLab collection → merge → S3 upload
    - Add smoke validation: load all 17 target files, verify MUNICIPALITY_EN_MAP covers all entries, verify signguCode mapping has expected entry count
    - _Requirements: 1.1, 1.3, 8.3, 8.4_

  - [ ]* 9.2 Write integration tests for end-to-end pipeline
    - Test province acquisition with mocked Wikipedia client (1 province, 2-3 cities)
    - Test DataLab collection with mocked API (1 month, known signguCodes)
    - Test full merge pipeline with sample data from both sources
    - Test S3 upload with mocked boto3 client
    - _Requirements: 2.3, 6.1, 8.3, 10.1_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Remediate nationwide Wikipedia acquisition quality gaps
  - [ ] 11.1 Correct disambiguation-page target titles
    - Update `crawling/KR/targets/gyeonggi_municipalities_ko.json` and `crawling/KR/targets/jeonnam_municipalities_ko.json` so `광주시` and `영광군` resolve to the actual municipality pages, not Korean Wikipedia disambiguation pages
    - Keep `MUNICIPALITY_EN_MAP` keys aligned with the corrected target titles
    - Verify `KR-41-GWANGJU-GYEONGGI` and `KR-46-YEONGGWANG` descriptions no longer contain `다른 뜻은 다음과 같다` or `다음 등을 가리킨다`
    - _Requirements: 4.6, 11.1, 11.2, 11.3_

  - [ ] 11.2 Add coordinate remediation for missing-coordinate municipalities
    - Add a fallback or remediation path for the 9 cities identified in `docs/reports/kr_wikipedia_nationwide_acquisition_review_20260629.md`
    - Preserve records when coordinates are still missing, but report them as quality remediation items
    - Verify missing coordinate count is reduced or explicitly documented
    - _Requirements: 4.8, 11.4_

  - [ ] 11.3 Fix empty-container field_status handling
    - Update field status logic so empty lists and empty objects are marked missing unless a field-specific rule says otherwise
    - Add tests for empty `site_urls`
    - Verify the 5 empty `site_urls` cases are no longer marked collected
    - _Requirements: 4.7, 11.5_

  - [ ] 11.4 Add province/all-provinces execution path tests
    - Test `--province-id KR-11` target resolution
    - Test `--all-provinces` iterates 17 province target files
    - Test `acquire_province()` skip/new/failed accounting
    - Test `acquire_all_provinces()` returns one ProvinceResult per province
    - _Requirements: 2.2, 2.3, 9.3, 11.6_

  - [ ] 11.5 Partial reacquisition and report update
    - Reacquire or patch the affected Wikipedia records after Tasks 11.1-11.3
    - Update the nationwide Wikipedia acquisition report so count completeness and content-quality completeness are reported separately
    - _Requirements: 11.7_

- [ ] 12. Remediate TourAPI unique city key and reacquisition path
  - [ ] 12.1 Present Korean file header drafts for user approval
    - Purpose: Python 파일 헤더를 적용하기 전에 사용자 검토 게이트를 통과한다.
    - Scope: `crawling/KR/tour_api_region_detail_acquisition.py`, `crawling/KR/tour_api_city_detail_acquisition.py`, `crawling/KR/datalab_collector.py`, `src/kr_details_pipeline/s3_keys.py`, `src/kr_details_pipeline/manifest.py`, `src/kr_details_pipeline/transform.py`, and modified tests
    - Acceptance: 대상 파일별 한국어 파일 헤더 문안이 사용자에게 제시되고 승인 전까지 Python 파일 docstring을 수정하지 않는다.
    - Verification: 승인 기록 또는 사용자 확인 메시지
    - _Requirements: 17.1, 17.2_

  - [ ] 12.2 Add province-aware TourAPI city identity helper
    - Purpose: TourAPI target을 `cities.json`의 disambiguated 도시와 정확히 연결한다.
    - Scope: `crawling/KR/tour_api_region_detail_acquisition.py`
    - Acceptance: 동명이구 대상의 `city_key`가 모두 고유하고, lookup은 `city_name_ko` 단독 키를 사용하지 않는다.
    - Verification: identity 중복 검사와 관련 단위 테스트
    - _Requirements: 12.2, 12.3, 13.1, 13.2, 13.3, 13.4_

  - [ ] 12.3 Change TourAPI list/detail output paths to `city_key`
    - Purpose: `jung-gu.json`, `dong-gu.json` 같은 단독 파일명 충돌을 제거한다.
    - Scope: `crawling/KR/tour_api_region_detail_acquisition.py`, `crawling/KR/tour_api_city_detail_acquisition.py`
    - Acceptance: `output_path`와 `list_path`가 standalone `city_name_en`으로 생성되지 않고, 표시명은 metadata로 보존된다.
    - Verification: 서울/울산 중구, 강원/경남 고성군 테스트
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ] 12.4 Make nationwide TourAPI reacquisition repeatable without disposable helper scripts
    - Purpose: 임시 `_run_nationwide.py` 없이 전국 재취득을 재현 가능하게 실행한다.
    - Scope: `crawling/KR/tour_api_region_detail_acquisition.py`
    - Acceptance: 전국 target 파일 또는 region option을 명시적으로 선택할 수 있다.
    - Verification: dry-run 또는 limit 기반 smoke 실행
    - _Requirements: 18.4_

  - [ ] 12.5 Fix DataLab visitor statistics association for TourAPI details
    - Purpose: raw/detail 내부 visitor_statistics가 동명이구에 잘못 붙는 것을 막는다.
    - Scope: `crawling/KR/tour_api_city_detail_acquisition.py`, `crawling/KR/datalab_collector.py`
    - Acceptance: 방문통계 결과에 city identity 추적 필드가 남고, 통계 부재는 raw/detail 생성을 실패시키지 않는다.
    - Verification: mocked DataLab 응답 단위 테스트
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ] 12.6 Make S3 raw manifest and keys use unique city identity
    - Purpose: S3 raw 업로드 결과에서 도시 식별자를 추적 가능하게 하고 key 충돌을 차단한다.
    - Scope: `src/kr_details_pipeline/s3_keys.py`, `src/kr_details_pipeline/manifest.py`, `src/kr_details_pipeline/tests/test_s3_keys.py`, `src/kr_details_pipeline/tests/test_manifest.py`
    - Acceptance: manifest가 `city_key`, `city_id`, `city_name_en`, `city_name_ko`, province, `lDongRegnCd`, `lDongSignguCd`를 포함하고, 동명이구 S3 key 중복이 0건이다.
    - Verification: `uv run pytest src/kr_details_pipeline/tests/test_s3_keys.py src/kr_details_pipeline/tests/test_manifest.py`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ] 12.7 Align transform and DynamoDB V2 key candidates
    - Purpose: 후단 load candidate가 standalone `city_name_en` PK로 수렴하지 않게 한다.
    - Scope: `src/kr_details_pipeline/transform.py`, `src/kr_details_pipeline/tests/test_transform.py`, optionally `src/kr_details_pipeline/load.py` or `src/kr_details_pipeline/domain_preprocess.py`
    - Acceptance: transformed records가 unique city key와 표시명을 모두 보존하고, 동명이구 PK 중복은 dry-run/load candidate 검증에서 보고된다.
    - Verification: `uv run pytest src/kr_details_pipeline/tests/test_transform.py` plus duplicate key dry-run if available
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

  - [ ] 12.8 Apply approved Korean headers, file history, and run reacquisition readiness verification
    - Purpose: 승인된 문서화 규칙을 적용하고 전국 재취득 전 smoke gate를 통과한다.
    - Scope: modified Python modules, modified tests, and completion report
    - Acceptance: 각 수정 파일 하단에 `# 파일 이력`과 `(github name)` 작업자 표기가 있고, smoke 대상이 별도 raw/detail 파일로 생성되며, 완료 보고서가 기존 `20260625`와 신규 ingest date를 구분한다.
    - Verification: `rg -n "파일 이력|2026-06-29" <target-files>` and smoke report for 서울 중구, 울산 중구, 강원 고성군, 경남 고성군
    - _Requirements: 17.3, 17.4, 17.5, 18.1, 18.2, 18.3, 18.5_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–14)
- Unit tests validate specific examples and edge cases
- The DataLab collector is extracted from `.cache/tour_api_korea_repo/scripts/scrape_and_aggregate_visitor.py` into a clean module under `crawling/KR/`
- All 17 target files already exist in `crawling/KR/targets/`; the implementation focuses on wiring them into the batch pipeline
- Python is the implementation language (matching existing codebase and design)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.2", "4.3", "5.2"] },
    { "id": 2, "tasks": ["2.2", "5.3", "5.4", "5.5"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "5.6", "5.7", "5.8", "5.9"] },
    { "id": 4, "tasks": ["7.1", "8.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "8.2", "8.3"] },
    { "id": 6, "tasks": ["9.1"] },
    { "id": 7, "tasks": ["9.2"] },
    { "id": 8, "tasks": ["11.1", "11.2", "11.3", "11.4", "11.5"] },
    { "id": 9, "tasks": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "12.8"] }
  ]
}
```

## Change History

- 2026-06-29: Added Task 11 to remediate nationwide Wikipedia quality gaps found in `docs/reports/kr_wikipedia_nationwide_acquisition_review_20260629.md`.
- 2026-06-29: Merged TourAPI unique city key bugfix tasks into the existing nationwide reacquisition Spec as Task 12.
