# Requirements Document

## Introduction

현재 한국(KR) 데이터 전처리 파이프라인은 세 개의 독립적인 모듈로 분리되어 있다: Wikipedia 파이프라인(`pipeline.py`), TourAPI 지역 상세 파이프라인(`tour_api_region_detail_acquisition.py`), TourAPI 상세 수확기(`tour_api_detail_harvester.py`). 이 세 모듈은 공통 오케스트레이터 없이 각각 독립적으로 실행되며, 데이터 부족 시 리뷰 상태로 전환하는 메커니즘이 없고, 이미지 URL 취득 및 저장 기능도 없다.

이 기능은 세 파이프라인을 하나의 통합 전처리 파이프라인으로 병합하고, 데이터 완전성 평가를 통해 정보가 부족한 레코드를 자동으로 리뷰 상태로 전환하며, Wikipedia 썸네일과 TourAPI `firstimage` 필드에서 이미지 URL을 취득하여 CityRecord에 저장하는 기능을 구현한다.

추가적으로, 기존 `TourKoreaDomainData` DynamoDB 테이블을 대체하는 신규 테이블을 의미 있는 GSI 명명 규칙으로 생성하고, 메타데이터 변경 사항을 반영한 벡터 인덱스 재빌드를 지원하며, S3 파이프라인 버킷에 이미 적재된 전처리 완료 데이터(`processed/KR/`)를 입력으로 하여 DynamoDB 적재와 벡터 빌드를 End-to-End로 실행 가능한 통합 파이프라인 확장을 포함한다.

## Glossary

- **Unified_Pipeline**: 세 개의 분리된 전처리 파이프라인(Wikipedia, TourAPI Region Detail, TourAPI Detail Harvester)을 하나로 통합한 오케스트레이터 모듈
- **Wikipedia_Stage**: Wikipedia에서 도시 메타데이터(설명, 좌표, 기후 등)를 수집하는 전처리 단계
- **TourAPI_Region_Stage**: TourAPI KorService2 엔드포인트에서 관광지·축제 목록과 상세 정보를 수집하는 전처리 단계
- **TourAPI_Detail_Stage**: tour-api-korea 리포지토리 아티팩트에서 도시별 상세 데이터를 추출하는 전처리 단계
- **Review_Transition**: 레코드의 데이터가 불충분할 때 해당 레코드의 상태를 STATUS_NEEDS_REVIEW로 자동 전환하는 메커니즘
- **Completeness_Evaluator**: CityRecord의 필수 필드 충족 여부를 평가하여 리뷰 전환 필요성을 판단하는 컴포넌트
- **Image_Resolver**: Wikipedia 썸네일 URL과 TourAPI firstimage URL을 취득하여 CityRecord에 저장하는 컴포넌트
- **CityRecord**: 도시 메타데이터를 담는 정규화된 데이터 구조 (city_id, city_name_ko, prefecture_id, location, latitude, longitude, description 등 포함)
- **Pipeline_Context**: 파이프라인 실행 중 각 단계 간 공유되는 상태 정보 (처리된 레코드, 에러 목록, 단계별 결과 등)
- **Stage**: 통합 파이프라인 내에서 순차적으로 실행되는 하나의 데이터 처리 단계
- **Domain_Table**: DynamoDB에 도메인별(도시, 관광지, 축제) 전처리 결과를 적재하는 테이블 (기존: TourKoreaDomainData)
- **New_Domain_Table**: 기존 TourKoreaDomainData와 동일한 스키마를 갖되 의미 있는 GSI 명명 규칙을 적용한 신규 DynamoDB 테이블
- **GSI**: Global Secondary Index의 약어. DynamoDB 테이블에서 대체 쿼리 패턴을 지원하는 보조 인덱스
- **Vector_Index**: S3 Vectors 버킷(`lovv-vector-dev`) 내 `kr-tour-domain-v1` 인덱스. Titan Embed v2 임베딩 벡터와 메타데이터를 저장
- **Vector_Rebuild**: 벡터 인덱스의 전체 또는 증분 재빌드를 수행하는 프로세스. DynamoDB에서 데이터를 내보내고 청크를 생성하여 임베딩 후 S3 Vectors에 업서트
- **DynamoDB_Loader**: 전처리된 도메인 데이터를 DynamoDB 테이블에 적재하는 컴포넌트
- **End_to_End_Pipeline**: S3 파이프라인 버킷의 전처리 완료 데이터(`processed/KR/`)를 입력으로 하여 DynamoDB 적재(load) → 벡터 빌드(vector-build)를 하나의 명령으로 실행하는 확장된 통합 파이프라인
- **Local_Test_Mode**: 단일 광역시/도(province) 데이터만을 대상으로 E2E 파이프라인 전체 흐름(S3 읽기 → DynamoDB 적재 → 벡터 빌드)을 로컬 환경에서 검증하는 실행 모드. `--local-test` 플래그와 `--province-id` 옵션 조합으로 활성화

## Requirements

### Requirement 1: 통합 파이프라인 오케스트레이션

**User Story:** As a data engineer, I want a single unified pipeline orchestrator that coordinates all three preprocessing stages, so that I can run the complete data collection flow with one command instead of managing three separate scripts.

#### Acceptance Criteria

1. THE Unified_Pipeline SHALL execute the Wikipedia_Stage, TourAPI_Region_Stage, and TourAPI_Detail_Stage in a defined sequential order
2. WHEN the user invokes the Unified_Pipeline, THE Unified_Pipeline SHALL accept a configuration specifying which stages to execute (all stages by default)
3. WHEN a stage completes, THE Unified_Pipeline SHALL pass the Pipeline_Context containing collected records to the next stage
4. WHILE executing multiple stages, THE Unified_Pipeline SHALL accumulate results from each stage and merge them into a unified CityRecord collection
5. IF a stage fails with a non-recoverable error, THEN THE Unified_Pipeline SHALL log the error, preserve results from previously completed stages, and report which stage failed

### Requirement 2: 단계별 독립 실행 지원

**User Story:** As a data engineer, I want to run individual pipeline stages independently, so that I can debug or rerun specific stages without executing the entire pipeline.

#### Acceptance Criteria

1. WHEN the user specifies --stage wikipedia, THE Unified_Pipeline SHALL execute only the Wikipedia_Stage
2. WHEN the user specifies --stage tourapi-region, THE Unified_Pipeline SHALL execute only the TourAPI_Region_Stage
3. WHEN the user specifies --stage tourapi-detail, THE Unified_Pipeline SHALL execute only the TourAPI_Detail_Stage
4. WHEN a single stage is executed independently, THE Unified_Pipeline SHALL load existing CityRecords from the output directory as the initial Pipeline_Context
5. WHEN multiple --stage arguments are provided, THE Unified_Pipeline SHALL execute only the specified stages in the defined sequential order

### Requirement 3: 데이터 완전성 평가

**User Story:** As a data engineer, I want the pipeline to evaluate record completeness after each stage, so that I can identify which records need manual review.

#### Acceptance Criteria

1. WHEN a stage completes processing a CityRecord, THE Completeness_Evaluator SHALL check the presence of required fields: city_name_ko, prefecture_id, latitude, longitude, and description
2. WHEN a CityRecord is missing latitude or longitude, THE Completeness_Evaluator SHALL mark the coordinates field_status as STATUS_NEEDS_REVIEW
3. WHEN a CityRecord has an empty or whitespace-only description, THE Completeness_Evaluator SHALL mark the description field_status as STATUS_NEEDS_REVIEW
4. THE Completeness_Evaluator SHALL compute a data_confidence score: "high" when all required fields are present and valid, "medium" when at least city_name_ko and prefecture_id are present, "low" when required fields are missing
5. WHEN a CityRecord has data_confidence of "low", THE Completeness_Evaluator SHALL set the overall record status to STATUS_NEEDS_REVIEW

### Requirement 4: 리뷰 상태 자동 전환

**User Story:** As a data engineer, I want records with insufficient data to be automatically transitioned to a review state, so that I can prioritize manual inspection of incomplete records.

#### Acceptance Criteria

1. WHEN the Completeness_Evaluator determines a CityRecord requires review, THE Review_Transition SHALL update the record's field_status dictionary with the specific fields requiring attention
2. THE Review_Transition SHALL generate a review_reason field indicating why the record was flagged (e.g., "missing_coordinates", "empty_description", "no_image_url")
3. WHEN a CityRecord transitions to STATUS_NEEDS_REVIEW, THE Unified_Pipeline SHALL append the record to a separate review manifest file (review_manifest.json) listing all records requiring manual attention
4. WHEN a subsequent pipeline run provides the missing data for a previously reviewed record, THE Review_Transition SHALL upgrade the record status from STATUS_NEEDS_REVIEW to STATUS_COLLECTED
5. THE review manifest SHALL include for each flagged record: city_id, city_name_ko, prefecture_id, missing fields, review_reason, and the timestamp when the record was flagged

### Requirement 5: Wikipedia 이미지 URL 취득

**User Story:** As a data engineer, I want the pipeline to fetch Wikipedia thumbnail image URLs for each city, so that the downstream application can display representative city images.

#### Acceptance Criteria

1. WHEN the Wikipedia_Stage processes a city page, THE Image_Resolver SHALL query the Wikipedia API pageimages endpoint to retrieve the page's primary thumbnail URL
2. WHEN a Wikipedia page has a thumbnail available, THE Image_Resolver SHALL store the URL in the CityRecord's image_url field
3. WHEN a Wikipedia page has no thumbnail, THE Image_Resolver SHALL set image_url to null and mark the image field_status as STATUS_MISSING
4. THE Image_Resolver SHALL request thumbnail images at a minimum width of 300 pixels to ensure adequate display quality
5. WHEN the Wikipedia API returns a redirect for a page title, THE Image_Resolver SHALL follow the redirect and retrieve the thumbnail from the resolved page

### Requirement 6: TourAPI 이미지 URL 취득

**User Story:** As a data engineer, I want the pipeline to extract image URLs from TourAPI responses, so that records without Wikipedia thumbnails can still have representative images.

#### Acceptance Criteria

1. WHEN the TourAPI_Region_Stage or TourAPI_Detail_Stage retrieves detail data containing a firstimage field, THE Image_Resolver SHALL extract the firstimage URL
2. WHEN a CityRecord already has an image_url from the Wikipedia_Stage, THE Image_Resolver SHALL preserve the Wikipedia image as primary and store the TourAPI image as a secondary source in image_urls list
3. WHEN a CityRecord has no image_url and a TourAPI firstimage is available, THE Image_Resolver SHALL set the firstimage URL as the CityRecord's image_url
4. WHEN the TourAPI firstimage URL is empty or null, THE Image_Resolver SHALL skip the image assignment for that source without error
5. THE Image_Resolver SHALL validate that extracted image URLs conform to a valid HTTP/HTTPS URL format before storing them

### Requirement 7: CityRecord 이미지 필드 확장

**User Story:** As a data engineer, I want the CityRecord data model to support image URL storage, so that collected image data can be persisted and consumed by downstream systems.

#### Acceptance Criteria

1. THE CityRecord SHALL include an image_url field of type string or null for the primary representative image
2. THE CityRecord SHALL include an image_urls field of type list containing all collected image URLs from different sources
3. WHEN a CityRecord is serialized to JSON, THE output SHALL include image_url and image_urls fields preserving backward compatibility with existing consumers
4. THE image_urls list entries SHALL include source attribution (e.g., "wikipedia", "tourapi") to identify the origin of each URL
5. WHEN loading existing cities.json that lacks image fields, THE Unified_Pipeline SHALL treat missing image_url as null and missing image_urls as an empty list without error

### Requirement 8: 파이프라인 실행 로깅 및 리포트

**User Story:** As a data engineer, I want comprehensive execution logging and a summary report after each pipeline run, so that I can monitor data quality and pipeline health.

#### Acceptance Criteria

1. WHEN the Unified_Pipeline completes execution, THE Unified_Pipeline SHALL output a summary report containing: total records processed, records per stage, records transitioned to review, and image URLs collected
2. THE Unified_Pipeline SHALL log the start and completion timestamp of each stage
3. WHEN records are transitioned to STATUS_NEEDS_REVIEW, THE summary report SHALL list the count of records per review_reason category
4. THE Unified_Pipeline SHALL log any API errors, network failures, or parsing errors encountered during execution with the affected city_id
5. IF the --verbose flag is specified, THEN THE Unified_Pipeline SHALL output per-record processing details including field_status changes and image resolution results

### Requirement 9: 증분 병합 및 기존 데이터 보존

**User Story:** As a data engineer, I want the unified pipeline to merge new results with existing data incrementally, so that previously collected data is preserved across multiple runs.

#### Acceptance Criteria

1. WHEN the Unified_Pipeline starts, THE Unified_Pipeline SHALL load existing cities.json as the base dataset for incremental merge
2. WHEN a stage produces a CityRecord that already exists in the base dataset, THE Unified_Pipeline SHALL update only the fields that are newly collected or have higher data_confidence without overwriting previously collected valid data
3. WHEN a field is updated during merge, THE Unified_Pipeline SHALL record the previous value source and the new value source in the field_status for auditability
4. THE Unified_Pipeline SHALL preserve all CityRecords from the base dataset even if they are not processed in the current run
5. WHEN the image_url field is populated by a new run and differs from the existing value, THE Unified_Pipeline SHALL append the new URL to image_urls and keep the existing image_url as primary unless explicitly overridden with --force-image-update

### Requirement 10: 파이프라인 구성 및 CLI 인터페이스

**User Story:** As a data engineer, I want a clear CLI interface for the unified pipeline, so that I can configure and execute the pipeline with appropriate options for different scenarios.

#### Acceptance Criteria

1. THE Unified_Pipeline SHALL accept --output-dir to specify the directory for JSON output files (default: data/KR/)
2. THE Unified_Pipeline SHALL accept --stage arguments to select which stages to execute
3. THE Unified_Pipeline SHALL accept --province-id to limit processing to a specific province
4. THE Unified_Pipeline SHALL accept --force-refresh to re-collect data for already-collected records
5. THE Unified_Pipeline SHALL accept --skip-images to disable image URL resolution for faster execution when images are not needed
6. WHEN the Unified_Pipeline is invoked without any arguments, THE Unified_Pipeline SHALL execute all stages for all provinces with default configuration

### Requirement 11: 신규 DynamoDB 테이블 생성 (GSI 명명 개선)

**User Story:** As a data engineer, I want a new DynamoDB table with descriptively named GSIs replacing the generic GSI1/GSI2/GSI3 naming, so that query patterns are self-documenting and maintainable without impacting other teams still developing on the existing table.

#### Acceptance Criteria

1. THE New_Domain_Table SHALL maintain the same PK/SK key schema (PK: String hash key, SK: String range key) as the existing TourKoreaDomainData table
2. THE New_Domain_Table SHALL use PAY_PER_REQUEST billing mode and enable point-in-time recovery
3. THE New_Domain_Table SHALL define a GSI named "CityDomainIndex" with hash_key=city_key and range_key=domain_sort_key replacing the existing GSI1
4. THE New_Domain_Table SHALL define a GSI named "ProvinceDomainIndex" with hash_key=province_key and range_key=domain_sort_key replacing the existing GSI2
5. THE New_Domain_Table SHALL define a GSI named "EntityTypeDomainIndex" with hash_key=entity_type and range_key=domain_sort_key replacing the existing GSI3
6. THE New_Domain_Table SHALL define a GSI named "FestivalMonthIndex" with hash_key=entity_type and range_key=gsi_sk preserving the existing festival month query pattern
7. THE New_Domain_Table SHALL include all existing attribute definitions: PK, SK, entity_type, city_key, province_key, domain_sort_key, gsi_sk
8. WHEN the Terraform configuration is applied, THE Terraform resource SHALL create the New_Domain_Table alongside the existing TourKoreaDomainData table without modifying or deleting the existing table
9. WHEN the New_Domain_Table is created, THE IAM policy for the pipeline Lambda role SHALL grant DynamoDB read and write access (PutItem, UpdateItem, GetItem, DeleteItem, Query, DescribeTable) to the New_Domain_Table and its indexes

### Requirement 12: 벡터 인덱스 재빌드 (메타데이터 변경 반영)

**User Story:** As a data engineer, I want to rebuild the vector index to reflect metadata changes from the new table schema and enrichment updates, so that the vector search results include up-to-date metadata fields for downstream retrieval.

#### Acceptance Criteria

1. WHEN a full rebuild is requested, THE Vector_Rebuild SHALL export all vectorizable items from the New_Domain_Table using the EntityTypeDomainIndex GSI
2. WHEN an incremental rebuild is requested, THE Vector_Rebuild SHALL export only items modified since the last rebuild timestamp recorded in the rebuild manifest
3. THE Vector_Rebuild SHALL generate embedding text chunks and metadata including: country, province, city_id, city_name_en, city_name_ko, entity_type, source_type, source_id, place_id, title, class_tags, theme_tags, season_tags, visit_months, latitude, longitude
4. THE Vector_Rebuild SHALL embed text chunks using the Amazon Titan Embed Text v2 model and upsert resulting vectors to the kr-tour-domain-v1 index in the lovv-vector-dev S3 Vectors bucket
5. WHEN the rebuild completes, THE Vector_Rebuild SHALL record a rebuild manifest containing: rebuild_mode (full or incremental), start_timestamp, end_timestamp, total_items_processed, items_upserted, items_skipped, and errors_encountered
6. IF an embedding API call fails for a specific item, THEN THE Vector_Rebuild SHALL log the error with the affected item PK/SK, skip the item, and continue processing remaining items
7. WHEN the Vector_Rebuild references the New_Domain_Table GSI, THE Vector_Rebuild SHALL use the descriptive GSI name "EntityTypeDomainIndex" instead of the legacy "GSI3" identifier

### Requirement 13: 통합 파이프라인 End-to-End 실행 (S3 적재 데이터→DynamoDB→벡터)

**User Story:** As a data engineer, I want to execute the pipeline from already-staged S3 processed data through DynamoDB loading to vector index rebuild with a single command, so that I can run the load-and-build lifecycle without re-running collection or preprocessing stages.

#### Acceptance Criteria

1. THE End_to_End_Pipeline SHALL read pre-processed data from the S3 pipeline bucket (`lovv-data-pipeline-{env}-{account_id}`) at the `processed/KR/` prefix as its input source
2. WHEN the user invokes the End_to_End_Pipeline without --stage arguments, THE End_to_End_Pipeline SHALL execute the full sequence: S3 processed data read → DynamoDB load → vector rebuild
3. WHEN the user specifies --stage load, THE End_to_End_Pipeline SHALL read processed JSON files from the S3 pipeline bucket at `processed/KR/details/{ingest_date}/passed/` and write domain-separated items to the New_Domain_Table
4. WHEN the user specifies --stage vector-build, THE End_to_End_Pipeline SHALL execute only the vector rebuild phase reading from the New_Domain_Table
5. THE End_to_End_Pipeline SHALL accept --bucket to specify the S3 pipeline bucket name and --ingest-date to specify the target ingest date partition (default: latest available date)
6. WHEN the DynamoDB load phase executes, THE DynamoDB_Loader SHALL list and read all `.json` files under `processed/KR/details/{ingest_date}/passed/` from the S3 bucket and write domain-separated items to the New_Domain_Table
7. WHEN the DynamoDB load phase completes, THE End_to_End_Pipeline SHALL pass the load result (items written, errors) to the vector rebuild phase as Pipeline_Context
8. IF the DynamoDB load phase fails with a non-recoverable error, THEN THE End_to_End_Pipeline SHALL log the error, preserve previously completed phase results, and skip the vector rebuild phase
9. WHEN all phases complete, THE End_to_End_Pipeline SHALL output a combined summary report including: S3 files read, records loaded to DynamoDB, vectors upserted, and total execution time

### Requirement 14: 단일 지역 로컬 테스트 게이트

**User Story:** As a data engineer, I want to validate the E2E pipeline locally using a single province's data before executing against all provinces, so that I can catch integration errors early without risking full-scale data corruption or wasted processing time.

#### Acceptance Criteria

1. THE End_to_End_Pipeline SHALL accept a `--local-test` flag that activates Local_Test_Mode restricting execution to a single province specified by `--province-id`
2. WHEN Local_Test_Mode is active, THE End_to_End_Pipeline SHALL execute the full sequence (S3 read → DynamoDB load → vector rebuild) scoped only to items matching the specified province_key
3. WHEN Local_Test_Mode is active, THE End_to_End_Pipeline SHALL read processed data only from `processed/KR/details/{ingest_date}/passed/` files that belong to the specified province
4. WHEN Local_Test_Mode completes without errors, THE End_to_End_Pipeline SHALL output a test summary report containing: province_id used, total items read from S3, items loaded to DynamoDB, vectors built, and a PASS/FAIL verdict
5. WHEN all items from the specified province are loaded to DynamoDB and all vectors are built without errors, THE test summary verdict SHALL be PASS
6. IF any DynamoDB write or vector embedding operation fails during Local_Test_Mode, THEN THE test summary verdict SHALL be FAIL with a list of failed item identifiers and error messages
7. THE Local_Test_Mode SHALL be executable locally using local AWS credentials (via AWS CLI profile or environment variables) without requiring Lambda deployment
8. WHEN `--local-test` is specified without `--province-id`, THE End_to_End_Pipeline SHALL terminate with an error message instructing the user to provide a province identifier
9. WHEN a Local_Test_Mode execution results in a FAIL verdict, THE End_to_End_Pipeline SHALL output a recommendation to resolve failures before running the full multi-province execution
