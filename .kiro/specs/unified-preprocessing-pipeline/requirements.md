# Requirements Document

## Introduction

현재 한국(KR) 데이터 전처리 파이프라인은 세 개의 독립적인 모듈로 분리되어 있다: Wikipedia 파이프라인(`pipeline.py`), TourAPI 지역 상세 파이프라인(`tour_api_region_detail_acquisition.py`), TourAPI 상세 수확기(`tour_api_detail_harvester.py`). 이 세 모듈은 공통 오케스트레이터 없이 각각 독립적으로 실행되며, 데이터 부족 시 리뷰 상태로 전환하는 메커니즘이 없고, 이미지 URL 취득 및 저장 기능도 없다.

이 기능은 세 파이프라인을 하나의 통합 전처리 파이프라인으로 병합하고, 데이터 완전성 평가를 통해 정보가 부족한 레코드를 자동으로 리뷰 상태로 전환하며, Wikipedia 썸네일과 TourAPI `firstimage` 필드에서 이미지 URL을 취득하여 CityRecord에 저장하는 기능을 구현한다.

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
