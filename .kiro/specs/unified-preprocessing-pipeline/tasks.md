# Implementation Plan: Unified Preprocessing Pipeline (Lambda-Based)

## Overview

This plan implements the unified preprocessing pipeline as AWS Lambda functions following existing project patterns (`src/kr_details_pipeline/`, `src/kr_vector_index/`). The new module `src/kr_unified_pipeline/` orchestrates preprocessing stages, completeness evaluation, image resolution, review transitions, DynamoDB V2 table loading, and vector index rebuild. Existing business logic from `kr_details_pipeline` and `kr_vector_index` is reused via imports rather than rewritten.

## Tasks

- [ ] 1. Create module structure and core data models
  - [ ] 1.1 Create `src/kr_unified_pipeline/` package with `__init__.py`, directory structure (`handlers/`, `tests/`)
    - Create `src/kr_unified_pipeline/__init__.py` with module docstring
    - Create `src/kr_unified_pipeline/handlers/__init__.py`
    - Create `src/kr_unified_pipeline/tests/__init__.py`
    - _Requirements: 1.1, 13.1_

  - [ ] 1.2 Define core data models in `src/kr_unified_pipeline/models.py`
    - Implement `CityRecord` dataclass with image fields (`image_url`, `image_urls: list[ImageSource]`)
    - Implement `ImageSource` frozen dataclass (`url: str`, `source: str`)
    - Implement `PipelineContext` dataclass (`city_records`, `stage_results`, `errors`, `config`, `start_time`, `review_manifest`)
    - Implement `PipelineConfig` dataclass with all CLI options mapped to fields
    - Implement `CompletenessResult` frozen dataclass (`data_confidence`, `missing_fields`, `field_statuses`, `needs_review`, `review_reasons`)
    - Implement `ReviewEntry` dataclass (`city_id`, `city_name_ko`, `prefecture_id`, `missing_fields`, `review_reason`, `flagged_at`)
    - Implement `StageResult` dataclass (`stage_name`, `started_at`, `completed_at`, `records_processed`, `records_updated`, `errors`, `images_collected`)
    - Implement `RebuildManifest` dataclass (`rebuild_mode`, `start_timestamp`, `end_timestamp`, `total_items_processed`, `items_upserted`, `items_skipped`, `errors_encountered`)
    - Implement `LocalTestSummary` dataclass (`province_id`, `items_read_from_s3`, `items_loaded_to_dynamodb`, `vectors_built`, `verdict`, `failed_items`, `execution_time_seconds`)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 4.5, 12.5, 14.4_

  - [ ] 1.3 Define `PipelineStage` Protocol in `src/kr_unified_pipeline/stages.py`
    - Define Protocol class with `name` property and `execute(context: PipelineContext) -> PipelineContext` method
    - Define canonical stage ordering constant: `STAGE_ORDER = ["wikipedia", "tourapi-region", "tourapi-detail", "load", "vector-build"]`
    - _Requirements: 1.1, 2.5_

- [ ] 2. Implement CompletenessEvaluator and ReviewTransition
  - [ ] 2.1 Implement `src/kr_unified_pipeline/completeness.py`
    - Implement `CompletenessEvaluator` class with `REQUIRED_FIELDS = ("city_name_ko", "prefecture_id", "latitude", "longitude", "description")`
    - Implement `evaluate(record: CityRecord) -> CompletenessResult` method checking field presence/validity
    - Implement `compute_confidence(record: CityRecord) -> str` returning "high"/"medium"/"low"
    - Mark coordinates as STATUS_NEEDS_REVIEW when latitude/longitude is None
    - Mark description as STATUS_NEEDS_REVIEW when empty or whitespace-only
    - Set overall status to STATUS_NEEDS_REVIEW when confidence is "low"
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 2.2 Write property test for CompletenessEvaluator field detection
    - **Property 3: Completeness evaluator field detection**
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [ ]* 2.3 Write property test for confidence classification
    - **Property 4: Confidence classification correctness**
    - **Validates: Requirements 3.4, 3.5**

  - [ ] 2.4 Implement `src/kr_unified_pipeline/review_transition.py`
    - Implement `ReviewTransition` class with `transition(record, result) -> None` method
    - Update record `field_status` dict with specific fields requiring attention
    - Generate `review_reason` field ("missing_coordinates", "empty_description", "no_image_url")
    - Implement `upgrade_if_complete(record, result) -> None` to restore STATUS_COLLECTED when data is now complete
    - Append flagged records to review manifest with city_id, city_name_ko, prefecture_id, missing_fields, review_reason, ISO 8601 timestamp
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 2.5 Write property test for review transition manifest completeness
    - **Property 5: Review transition and manifest completeness**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.5**

  - [ ]* 2.6 Write property test for review status upgrade round-trip
    - **Property 6: Review status upgrade round-trip**
    - **Validates: Requirements 4.4**

- [ ] 3. Implement ImageResolver
  - [ ] 3.1 Implement `src/kr_unified_pipeline/image_resolver.py`
    - Implement `ImageResolver` class with Wikipedia pageimages API integration (min width 300px, redirect following)
    - Implement `resolve_wikipedia_image(page_title, lang="ko") -> str | None`
    - Implement `resolve_tourapi_image(detail_data: dict) -> str | None` extracting firstimage field
    - Implement `apply_to_record(record, source, url) -> None` with hierarchy: Wikipedia=primary, TourAPI=secondary
    - Implement URL validation (HTTP/HTTPS only) before storing
    - Handle null/empty TourAPI firstimage gracefully without error
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 3.2 Write property test for image URL hierarchy
    - **Property 7: Image URL hierarchy**
    - **Validates: Requirements 6.2, 6.3**

  - [ ]* 3.3 Write property test for image URL validation
    - **Property 8: Image URL validation**
    - **Validates: Requirements 6.5**

  - [ ]* 3.4 Write property test for CityRecord serialization round-trip
    - **Property 9: CityRecord serialization round-trip with image fields**
    - **Validates: Requirements 7.3, 7.4, 7.5**

- [ ] 4. Checkpoint - Core business logic
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement incremental merge logic
  - [ ] 5.1 Implement `src/kr_unified_pipeline/merge.py`
    - Implement incremental merge: load existing `cities.json` as base dataset
    - Update only fields with equal or higher `data_confidence`; never overwrite valid data with empty/lower-confidence values
    - Record previous value source and new value source in `field_status` for auditability
    - Preserve all CityRecords from base dataset even if not processed in current run
    - Handle image merge: without `--force-image-update`, append new URL to `image_urls` and keep existing `image_url` as primary
    - With `--force-image-update`, replace `image_url` with new URL
    - Handle missing `cities.json` gracefully (start with empty base dataset)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 5.2 Write property test for incremental merge preservation
    - **Property 10: Incremental merge preserves existing records**
    - **Validates: Requirements 9.1, 9.4**

  - [ ]* 5.3 Write property test for merge confidence precedence
    - **Property 11: Merge prefers higher confidence data**
    - **Validates: Requirements 9.2**

  - [ ]* 5.4 Write property test for image merge without force flag
    - **Property 12: Image merge without force flag**
    - **Validates: Requirements 9.5**

- [ ] 6. Implement pipeline orchestrator and stage wrappers
  - [ ] 6.1 Implement `src/kr_unified_pipeline/orchestrator.py`
    - Implement `UnifiedPipeline` class that coordinates stage execution in canonical order
    - Accept configuration specifying which stages to execute (all by default)
    - Pass `PipelineContext` between stages accumulating results
    - Run `CompletenessEvaluator` after each preprocessing stage
    - Run `ImageResolver` during Wikipedia/TourAPI stages (unless `--skip-images`)
    - Run `ReviewTransition` for records needing review
    - Handle non-recoverable stage failure: log error, preserve prior results, report failed stage
    - Merge results into unified CityRecord collection
    - Output summary report on completion
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4_

  - [ ] 6.2 Implement stage wrappers in `src/kr_unified_pipeline/stages.py`
    - Implement `WikipediaStage` wrapping existing `crawling/KR/pipeline.py` logic
    - Implement `TourAPIRegionStage` wrapping `tour_api_region_detail_acquisition.py` logic
    - Implement `TourAPIDetailStage` wrapping `tour_api_detail_harvester.py` logic
    - Each stage loads existing CityRecords from output directory when executed independently
    - Each stage respects `--province-id` to limit processing scope
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 7. Implement Terraform infrastructure for DynamoDB V2 table
  - [ ] 7.1 Add `TourKoreaDomainDataV2` DynamoDB table resource in `infrastructure/terraform/main.tf`
    - Same PK/SK key schema (PK: String hash, SK: String range)
    - PAY_PER_REQUEST billing mode, point-in-time recovery enabled
    - GSI "CityDomainIndex" (hash_key=city_key, range_key=domain_sort_key)
    - GSI "ProvinceDomainIndex" (hash_key=province_key, range_key=domain_sort_key)
    - GSI "EntityTypeDomainIndex" (hash_key=entity_type, range_key=domain_sort_key)
    - GSI "FestivalMonthIndex" (hash_key=entity_type, range_key=gsi_sk)
    - All attribute definitions: PK, SK, entity_type, city_key, province_key, domain_sort_key, gsi_sk
    - Must NOT modify or delete existing TourKoreaDomainData table
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [ ] 7.2 Update IAM policy in `infrastructure/terraform/main.tf`
    - Add DynamoDB permissions (PutItem, UpdateItem, GetItem, DeleteItem, Query, DescribeTable) for the new table ARN
    - Add GSI query permission for the new table's indexes (`/index/*`)
    - _Requirements: 11.9_

  - [ ] 7.3 Add Lambda function resource for unified pipeline handler
    - Define `aws_lambda_function.kr_unified_pipeline` with handler `kr_unified_pipeline.handlers.pipeline_handler.handler`
    - Python 3.12 runtime, timeout 900s, memory 1024MB
    - Environment variables: `DYNAMODB_TABLE=TourKoreaDomainDataV2`, `PIPELINE_BUCKET`, `VECTOR_BUCKET`, `VECTOR_INDEX`
    - Create separate `archive_file` data source for the unified pipeline ZIP
    - Add CloudWatch Log Group with 14-day retention
    - Update `locals.lambda_names` map with new entry
    - _Requirements: 13.1, 13.2_

  - [ ] 7.4 Add Terraform variable for new table name in `infrastructure/terraform/variables.tf`
    - Add `domain_dynamodb_table_name_v2` variable with default "TourKoreaDomainDataV2"
    - _Requirements: 11.8_

- [ ] 8. Checkpoint - Infrastructure validated
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement E2E pipeline Lambda handler (S3 → DynamoDB → Vector)
  - [ ] 9.1 Implement `src/kr_unified_pipeline/s3_reader.py`
    - Implement `S3ProcessedReader` class to list and read JSON files from `processed/KR/details/{ingest_date}/passed/` prefix
    - Accept `bucket` and `ingest_date` parameters
    - Support province filtering for local-test mode (filter by province_key in items)
    - Return parsed domain items ready for DynamoDB load
    - _Requirements: 13.1, 13.3, 13.6, 14.3_

  - [ ] 9.2 Implement `src/kr_unified_pipeline/dynamodb_loader.py`
    - Implement `DynamoDBLoader` class that reuses `kr_details_pipeline.load._write_item` for DynamoDB writes
    - Accept items from S3 reader and write to New_Domain_Table
    - Track loaded/failed counts and return `LoadResult`
    - Import and reuse existing `_coerce_value` and `_write_item` from `kr_details_pipeline.load`
    - _Requirements: 13.3, 13.6, 13.7_

  - [ ] 9.3 Implement `src/kr_unified_pipeline/vector_rebuilder.py`
    - Implement `VectorRebuilder` class that reuses `kr_vector_index` modules (export, chunks, embed, upsert)
    - Support full and incremental rebuild modes
    - Use "EntityTypeDomainIndex" GSI name for queries against new table
    - Generate embedding metadata with all required fields (country, province, city_id, city_name_en, city_name_ko, entity_type, source_type, source_id, place_id, title, class_tags, theme_tags, season_tags, visit_months, latitude, longitude)
    - Record rebuild manifest on completion
    - Skip failed embedding items and continue processing
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 9.4 Write property test for rebuild manifest completeness
    - **Property 14: Rebuild manifest completeness**
    - **Validates: Requirements 12.5**

  - [ ] 9.5 Implement `src/kr_unified_pipeline/handlers/pipeline_handler.py`
    - Implement `handler(event: dict[str, Any], context: Any) -> dict[str, Any]` following existing handler pattern
    - Support commands: `"load"`, `"vector-build"`, `"e2e"` (full sequence)
    - Read config from event and environment variables (`DYNAMODB_TABLE`, `PIPELINE_BUCKET`, `VECTOR_BUCKET`, `VECTOR_INDEX`)
    - Orchestrate: S3 read → DynamoDB load → Vector rebuild
    - Handle non-recoverable errors: log, preserve completed phase results, skip subsequent phases
    - Return combined summary report (S3 files read, records loaded, vectors upserted, execution time)
    - _Requirements: 13.2, 13.3, 13.4, 13.5, 13.7, 13.8, 13.9_

- [ ] 10. Update `kr_vector_index/export.py` for backward-compatible GSI support
  - [ ] 10.1 Update `iter_gsi3_items` in `src/kr_vector_index/export.py` to accept configurable index name
    - Add `index_name: str = "GSI3"` parameter to `iter_gsi3_items` function
    - Default to "GSI3" for backward compatibility with existing table
    - When called from unified pipeline, pass `index_name="EntityTypeDomainIndex"`
    - Update `export_items` function signature to accept optional `index_name` parameter
    - Ensure existing callers (vector_index_handler.py, cli.py) continue to work without changes
    - _Requirements: 12.7_

- [ ] 11. Implement local-test mode and CLI
  - [ ] 11.1 Implement `src/kr_unified_pipeline/local_test.py`
    - Implement `LocalTestRunner` class that executes full E2E scoped to single province
    - Accept `province_id` parameter and filter all operations by province_key
    - Execute sequence: S3 read → DynamoDB load → Vector rebuild (province-scoped)
    - Output `LocalTestSummary` with verdict (PASS/FAIL), item counts, failed items
    - Verdict is PASS only when zero failures across all operations
    - Output recommendation to resolve failures before full execution when FAIL
    - Use local AWS credentials (CLI profile or environment variables)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.9_

  - [ ]* 11.2 Write property test for local test province scoping
    - **Property 15: Local test mode province scoping**
    - **Validates: Requirements 14.2, 14.3**

  - [ ]* 11.3 Write property test for local test verdict correctness
    - **Property 16: Local test verdict correctness**
    - **Validates: Requirements 14.4, 14.5, 14.6**

  - [ ] 11.4 Implement `src/kr_unified_pipeline/cli.py`
    - Implement argparse CLI with subcommands: `preprocess`, `e2e`, `local-test`
    - `preprocess` subcommand: `--stage`, `--output-dir`, `--province-id`, `--force-refresh`, `--skip-images`, `--verbose`, `--force-image-update`
    - `e2e` subcommand: `--stage` (load/vector-build), `--bucket`, `--ingest-date`, `--table-name`, `--rebuild-mode`
    - `local-test` subcommand: `--province-id` (required), `--bucket`, `--ingest-date`, `--table-name`
    - Validate `--local-test` requires `--province-id` (exit with instructional error if missing)
    - Follow pattern from `src/kr_details_pipeline/cli.py` and `src/kr_vector_index/cli.py`
    - Support `--profile` and `--region` for AWS session configuration
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 14.1, 14.8_

- [ ] 12. Implement pipeline execution logging and summary report
  - [ ] 12.1 Implement `src/kr_unified_pipeline/reporting.py`
    - Implement summary report generation: total records processed, records per stage, review transitions, images collected
    - Log start/completion timestamp of each stage
    - List count of records per `review_reason` category
    - Log API errors, network failures, parsing errors with affected `city_id`
    - Support `--verbose` mode for per-record processing details
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 12.2 Write property test for summary report review counts accuracy
    - **Property 17: Summary report review counts accuracy**
    - **Validates: Requirements 8.3**

- [ ] 13. Integration wiring and final validation
  - [ ] 13.1 Wire orchestrator to Lambda handler
    - Ensure `pipeline_handler.handler` delegates to `orchestrator.UnifiedPipeline` for preprocessing commands
    - Ensure `pipeline_handler.handler` delegates to `s3_reader` → `dynamodb_loader` → `vector_rebuilder` for E2E commands
    - Import from `kr_details_pipeline.load` and `kr_vector_index` modules (no code duplication)
    - _Requirements: 1.1, 13.2_

  - [ ] 13.2 Wire CLI to orchestrator and local-test runner
    - Connect CLI subcommands to appropriate orchestrator/runner classes
    - Ensure CLI creates boto3 session and passes clients to business logic
    - Test CLI argument parsing for all subcommands
    - _Requirements: 10.6, 14.7_

  - [ ]* 13.3 Write unit tests for CLI argument parsing and handler event routing
    - Test each CLI subcommand with valid/invalid argument combinations
    - Test handler event parsing for load, vector-build, and e2e commands
    - Test error cases: missing province-id with local-test, unknown stage values
    - _Requirements: 10.1, 10.2, 10.3, 14.8_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The module `src/kr_unified_pipeline/` follows the same pattern as `src/kr_details_pipeline/` and `src/kr_vector_index/`
- Lambda handler follows `def handler(event: dict[str, Any], context: Any) -> dict[str, Any]` signature
- Existing `kr_details_pipeline.load._write_item` and `kr_vector_index.export` are imported, not rewritten
- Terraform resources are added alongside existing ones without modifying the current table

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "3.1", "7.1", "7.4"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.2", "3.3", "3.4", "7.2"] },
    { "id": 3, "tasks": ["2.5", "2.6", "5.1", "7.3"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4", "6.1", "6.2"] },
    { "id": 5, "tasks": ["9.1", "10.1"] },
    { "id": 6, "tasks": ["9.2", "9.3"] },
    { "id": 7, "tasks": ["9.4", "9.5", "11.1"] },
    { "id": 8, "tasks": ["11.2", "11.3", "11.4", "12.1"] },
    { "id": 9, "tasks": ["12.2", "13.1", "13.2"] },
    { "id": 10, "tasks": ["13.3"] }
  ]
}
```
