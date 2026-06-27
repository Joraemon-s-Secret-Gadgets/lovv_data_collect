# Requirements Document

## Introduction

수집된 한국(KR) 도시·관광지·방문자 통계 데이터를 DynamoDB와 S3 Vector Store에 적재하는 전처리/적재 파이프라인을 구축한다. 현재 데이터 수집 단계(Wikipedia 도시 메타데이터, TourAPI 관광지 상세, DataLab 방문자 통계)는 `data/KR/details/` 하위에 도시별 JSON 파일로 저장되어 있으며, 일부 도시(Andong)에 대해서는 수동 ELT 결과(`data/KR/elt/`)가 존재한다. 이 파이프라인은 전국 약 211개 도시의 수집 데이터를 일괄적으로 정규화(normalize)하고, DynamoDB 단일 테이블(`TourKoreaDomainData`)에 적재하며, Bedrock Titan Embed v2 기반 임베딩을 생성하여 S3 Vector Store에 적재하는 End-to-End 자동화를 목표로 한다.

기존 `src/kr_vector_index` 모듈(chunks, embed, upsert, export)과 `data/KR/elt/` 정규화 포맷을 재활용하여 일관된 데이터 파이프라인을 구성한다.

## Glossary

- **Preprocessing_Pipeline**: 수집된 원본 JSON 데이터를 정규화하고 DynamoDB 및 S3 Vector Store에 적재하는 전체 파이프라인 시스템
- **Normalizer**: 도시별 원본 JSON(`data/KR/details/{city}.json`)을 DynamoDB 스키마에 맞는 JSONL 레코드로 변환하는 컴포넌트
- **DynamoDB_Loader**: 정규화된 레코드를 DynamoDB `TourKoreaDomainData` 테이블에 batch write하는 컴포넌트
- **Vector_Loader**: 정규화된 레코드를 임베딩하여 S3 Vector Store(`s3vectors`)에 적재하는 컴포넌트
- **TourKoreaDomainData**: DynamoDB 단일 테이블. PK=`CITY#{city_name_en}`, SK 패턴은 `METADATA#city`, `ATTRACTION#{content_id}`, `FESTIVAL#{content_id}`, `STAT#{YYYYMM}`
- **VectorChunk**: S3 Vector Store에 적재되는 단위. key, embedding_text, float32 벡터, metadata로 구성
- **Source_JSON**: `data/KR/details/{city_name_en}.json` 형식의 도시별 수집 결과 파일
- **Normalized_Record**: DynamoDB에 적재 가능한 PK/SK/속성이 포함된 단일 레코드(JSONL 한 줄)
- **Quality_Gate**: 레코드의 필수 필드 충족 여부를 평가하여 적재 가능 여부를 판단하는 검증 단계
- **Manifest**: 파이프라인 실행 결과를 기록하는 메타데이터 파일(처리 건수, 성공/실패 내역, S3 URI 등)
- **Batch_Writer**: DynamoDB BatchWriteItem API를 사용하여 최대 25건씩 레코드를 적재하는 컴포넌트
- **Embedding_Client**: Amazon Bedrock `amazon.titan-embed-text-v2:0` 모델을 호출하여 텍스트를 벡터로 변환하는 클라이언트

## Requirements

### Requirement 1: 도시별 원본 데이터 정규화

**User Story:** As a data engineer, I want the pipeline to normalize raw city detail JSON files into DynamoDB-compatible records, so that all collected data follows a consistent schema for structured queries.

#### Acceptance Criteria

1. WHEN a Source_JSON file is provided and contains a valid `meta` block, THE Normalizer SHALL extract city metadata and produce a Normalized_Record with PK=`CITY#{city_name_en}` and SK=`METADATA#city`
2. WHEN a Source_JSON file contains attractions, THE Normalizer SHALL produce one Normalized_Record per attraction with PK=`CITY#{city_name_en}` and SK=`ATTRACTION#{content_id}`
3. WHEN a Source_JSON file contains festivals, THE Normalizer SHALL produce one Normalized_Record per festival with PK=`CITY#{city_name_en}` and SK=`FESTIVAL#{content_id}`
4. WHEN a Source_JSON file contains visitor_statistics, THE Normalizer SHALL produce one Normalized_Record per month entry with PK=`CITY#{city_name_en}` and SK=`STAT#{YYYYMM}`, where month is a 6-digit string in YYYYMM format
5. THE Normalizer SHALL include entity_type, entity_id, city_id, city_name_ko, city_name_en, province, province_key, quality_status, and source_key fields in every Normalized_Record, where quality_status is one of "passed", "review", or "failed"
6. WHEN an attraction or festival record has a valid latitude and longitude within Korea boundary (124.0 ≤ longitude ≤ 132.0, 33.0 ≤ latitude ≤ 39.0) and both values are non-zero, THE Normalizer SHALL include the coordinates in the Normalized_Record
7. IF an attraction or festival record is missing content_id, THEN THE Normalizer SHALL skip the record, assign quality_status "failed", and log a warning with the city name and record index
8. IF a Source_JSON file is missing the `meta` block, THEN THE Normalizer SHALL produce a failed record indicating the missing metadata and skip content-level normalization for that file
9. IF an attraction or festival record has coordinates outside the Korea boundary or equal to zero, THEN THE Normalizer SHALL produce the Normalized_Record without coordinates and assign quality_status "review"

### Requirement 2: 데이터 품질 게이트

**User Story:** As a data engineer, I want a quality gate that validates records before loading, so that only records meeting minimum quality standards are persisted to DynamoDB and the vector store.

#### Acceptance Criteria

1. THE Quality_Gate SHALL verify that each Normalized_Record contains non-null and non-whitespace-only values for PK, SK, entity_type, and entity_id fields, and SHALL mark any record missing one or more of these fields with quality_status "failed"
2. WHEN an attraction Normalized_Record has a null, empty, or whitespace-only title or address field, THE Quality_Gate SHALL mark the record quality_status as "failed" and add the corresponding failure reason (e.g., "missing_title") to review_queues
3. WHEN a city_metadata Normalized_Record has a null, empty, or whitespace-only city_name_ko or province field, THE Quality_Gate SHALL mark the record quality_status as "failed" and add the corresponding failure reason to review_queues
4. WHEN a festival Normalized_Record has a null, empty, or whitespace-only title or content_id field, THE Quality_Gate SHALL mark the record quality_status as "failed" and add the corresponding failure reason to review_queues
5. WHEN a visitor_statistics Normalized_Record has a null, empty, or whitespace-only month field, THE Quality_Gate SHALL mark the record quality_status as "failed" and add "source_review" to review_queues
6. THE Quality_Gate SHALL mark records with quality_status "passed" when all required fields for the entity_type are present with non-null, non-whitespace-only values, and SHALL mark records with quality_status "review" when required fields are present but optional quality checks (location coordinates, theme, contact information) fail
7. WHEN the Quality_Gate marks a record as "failed", THE Preprocessing_Pipeline SHALL exclude the record from DynamoDB loading and vector indexing
8. THE Quality_Gate SHALL produce a quality summary report containing counts of passed, failed, and review records per entity_type

### Requirement 3: DynamoDB 일괄 적재

**User Story:** As a data engineer, I want the pipeline to batch-load normalized records into DynamoDB, so that the structured data is queryable for the downstream application.

#### Acceptance Criteria

1. THE DynamoDB_Loader SHALL write Normalized_Records to the `TourKoreaDomainData` table using BatchWriteItem API with a maximum of 25 items per batch
2. WHEN a batch write encounters an UnprocessedItems response, THE DynamoDB_Loader SHALL retry the unprocessed items with exponential backoff up to 3 retries
3. IF a batch write fails after all retries, THEN THE DynamoDB_Loader SHALL log the failed items and continue processing subsequent batches
4. THE DynamoDB_Loader SHALL include a `table` field with value "TourKoreaDomainData" in each item written
5. WHEN the DynamoDB_Loader processes records for a city that already exists in the table, THE DynamoDB_Loader SHALL overwrite existing items with the same PK and SK (upsert behavior)
6. THE DynamoDB_Loader SHALL track and report the total number of items written, failed, and skipped per city

### Requirement 4: S3 Vector Store 임베딩 및 적재

**User Story:** As a data engineer, I want the pipeline to generate embeddings and load them into S3 Vector Store, so that the data is available for semantic search and RAG applications.

#### Acceptance Criteria

1. WHEN a Normalized_Record has entity_type in ("city_metadata", "attraction", "festival") and quality_status "passed", THE Vector_Loader SHALL generate an embedding using the Embedding_Client
2. THE Vector_Loader SHALL construct embedding text following the existing `build_embedding_text` format: 이름, 유형, 도시, 지역, 주소, 분류, 설명 fields, plus entity-type-specific fields (기간/장소/계절 for festival, 테마 for attraction, 도시 ID for city_metadata)
3. THE Vector_Loader SHALL call Amazon Bedrock `amazon.titan-embed-text-v2:0` model with normalize=true to produce a 1024-dimension float32 vector for each embedding text
4. THE Vector_Loader SHALL construct a vector record with key=`{normalized_entity_type}#{source_id}#0` where normalized_entity_type maps "city_metadata" to "city" and other types remain unchanged, data.float32=embedding vector, and metadata following the existing VectorChunk schema with filterable metadata not exceeding 2048 bytes
5. THE Vector_Loader SHALL upload vectors to S3 Vector Store using `put_vectors` with configured vector_bucket and index_name in batches of up to 500 records
6. WHEN the Embedding_Client returns a throttling error, THE Vector_Loader SHALL retry with exponential backoff starting at 1 second (2^attempt seconds) up to a maximum of 5 retries
7. THE Vector_Loader SHALL exclude visitor_statistics records from vector indexing
8. IF all retry attempts are exhausted for an embedding request, THEN THE Vector_Loader SHALL log the failure with the record key and entity_type, skip the failed record, and continue processing remaining records
9. IF a `put_vectors` batch upload fails, THEN THE Vector_Loader SHALL retry the failed batch up to 3 times with exponential backoff starting at 1 second before raising an error that reports the batch index and number of affected records

### Requirement 5: 전국 일괄 처리 오케스트레이션

**User Story:** As a data engineer, I want to run the preprocessing pipeline for all 211 cities at once, so that I can load the entire national dataset in a single execution.

#### Acceptance Criteria

1. WHEN the user invokes the Preprocessing_Pipeline without city filters, THE Preprocessing_Pipeline SHALL discover and process all `*.json` files in the `data/KR/details/` directory, treating each file's stem (filename without extension) as the city_name_en
2. WHEN the user specifies one or more --city-name-en filter values, THE Preprocessing_Pipeline SHALL process only Source_JSON files whose filename stem matches a provided value (case-insensitive comparison)
3. IF the user specifies a --city-name-en value that does not match any existing Source_JSON file, THEN THE Preprocessing_Pipeline SHALL log a warning identifying the unmatched value and continue processing any matched files
4. WHEN the user specifies --province filter with a province English name (as defined in PROVINCES tuple, e.g. "Seoul", "Gyeonggi-do"), THE Preprocessing_Pipeline SHALL process only cities belonging to the specified province by resolving city-to-province membership via MUNICIPALITY_EN_MAP
5. IF the user specifies a --province value that does not match any known province English name, THEN THE Preprocessing_Pipeline SHALL exit with a non-zero status code and an error message listing valid province names
6. THE Preprocessing_Pipeline SHALL execute stages in order per city: normalize → quality gate → DynamoDB load → vector load
7. WHILE processing multiple cities, THE Preprocessing_Pipeline SHALL continue processing remaining cities when one city fails at any stage, and include each failure (city name, stage name, and error description) in the final execution summary
8. WHEN the --dry-run flag is specified, THE Preprocessing_Pipeline SHALL execute normalize and quality gate stages but skip DynamoDB load and vector load stages, and indicate dry-run mode in the final execution summary output

### Requirement 6: 증분 실행 및 멱등성

**User Story:** As a data engineer, I want the pipeline to support incremental runs and be idempotent, so that I can safely re-run the pipeline without creating duplicate data.

#### Acceptance Criteria

1. WHEN the Preprocessing_Pipeline writes to DynamoDB with the same PK and SK, THE DynamoDB_Loader SHALL overwrite the existing item without creating duplicates
2. WHEN the Vector_Loader uploads a vector with the same key, THE Vector_Loader SHALL overwrite the existing vector in S3 Vector Store
3. WHEN the --since flag is specified with a date in ISO 8601 format (YYYY-MM-DD), THE Preprocessing_Pipeline SHALL process only Source_JSON files whose last-modified timestamp is after the specified date
4. WHEN a pipeline execution completes, THE Preprocessing_Pipeline SHALL produce a Manifest file recording: execution timestamp, cities processed, records per entity_type, success/failure counts, and S3 vector manifest URI
5. WHEN the pipeline is executed twice with identical input data, THE resulting DynamoDB item attributes and S3 Vector Store object contents SHALL be byte-for-byte identical, excluding service-managed metadata such as write timestamps
6. IF the --since flag value is not a valid ISO 8601 date or refers to a future date, THEN THE Preprocessing_Pipeline SHALL reject the execution with an error message indicating the accepted date format and valid range
7. IF the --since flag is specified and no Source_JSON files have a last-modified timestamp after the specified date, THEN THE Preprocessing_Pipeline SHALL complete successfully with zero records processed and produce a Manifest file reflecting zero counts

### Requirement 7: 정규화 출력 파일 생성

**User Story:** As a data engineer, I want the pipeline to produce intermediate normalized JSONL files, so that I can inspect and debug the transformation results before loading.

#### Acceptance Criteria

1. THE Normalizer SHALL write normalized records to `data/KR/elt/{city_name_lower}/normalized/` directory as JSONL files separated by entity_type: city_metadata.jsonl, attractions.jsonl, festivals.jsonl, visitor_statistics.jsonl, where each line contains exactly one valid JSON object
2. THE Normalizer SHALL write DynamoDB-ready load records to `data/KR/elt/{city_name_lower}/load/tour_korea_domain_items.jsonl` combining all entity types that have quality_status "passed", with each record including a "table" field set to the target DynamoDB table name
3. WHEN a record's quality_status is "failed", THE Preprocessing_Pipeline SHALL write it to `data/KR/elt/{city_name_lower}/failed/invalid_records.jsonl` with the record's review_queues field indicating the failure reason(s)
4. THE Normalizer SHALL write a quality summary to `data/KR/elt/{city_name_lower}/quality/summary.json` containing: city_id, city_name_en, per-entity-type record counts (city_metadata, attractions, festivals, visitor_statistics), failed count, review count, load_items total, and table_name
5. WHEN the --skip-local-output flag is specified, THE Preprocessing_Pipeline SHALL skip writing files to the normalized/, load/, failed/, and quality/ directories and instead pass records directly from memory to the next pipeline stage
6. IF the output directory `data/KR/elt/{city_name_lower}/` does not exist, THEN THE Preprocessing_Pipeline SHALL create the full directory structure (normalized/, load/, failed/, quality/) before writing any files
7. WHEN writing to any output JSONL file, THE Normalizer SHALL overwrite the previous content for that city rather than appending, ensuring each pipeline run produces a complete and self-consistent output set

### Requirement 8: 파이프라인 CLI 인터페이스

**User Story:** As a data engineer, I want a clear CLI interface to configure and run the pipeline, so that I can control execution parameters for different scenarios.

#### Acceptance Criteria

1. THE Preprocessing_Pipeline SHALL accept --input-dir to specify the source JSON directory (default: `data/KR/details`)
2. THE Preprocessing_Pipeline SHALL accept --output-dir to specify the ELT output directory (default: `data/KR/elt`)
3. THE Preprocessing_Pipeline SHALL accept --table-name to specify the DynamoDB table (default: `TourKoreaDomainData`)
4. THE Preprocessing_Pipeline SHALL accept --vector-bucket to specify the S3 Vector bucket name, with no default value, requiring explicit user input when the pipeline targets S3 Vector upload
5. THE Preprocessing_Pipeline SHALL accept --index-name to specify the S3 Vector index name (default: `kr-tour-domain-v1`)
6. THE Preprocessing_Pipeline SHALL accept --region to specify the AWS region (default: `us-east-1`)
7. THE Preprocessing_Pipeline SHALL accept --profile to specify the AWS CLI profile for credential resolution
8. THE Preprocessing_Pipeline SHALL accept --concurrency to specify the number of parallel city processing workers as an integer between 1 and 16 inclusive (default: 1)
9. IF required AWS credentials cannot be resolved via the boto3 credential chain (environment variables, shared credentials file, or the profile specified by --profile), THEN THE Preprocessing_Pipeline SHALL print an error message to stderr indicating which credential element is missing and exit with a non-zero exit code before any data processing begins
10. IF --concurrency is provided with a value less than 1 or greater than 16, THEN THE Preprocessing_Pipeline SHALL print an error message to stderr indicating the valid range and exit with a non-zero exit code
11. IF --input-dir points to a path that does not exist or is not a directory, THEN THE Preprocessing_Pipeline SHALL print an error message to stderr indicating the invalid path and exit with a non-zero exit code before processing begins

### Requirement 9: 에러 처리 및 로깅

**User Story:** As a data engineer, I want comprehensive error handling and logging, so that I can diagnose failures and monitor pipeline health.

#### Acceptance Criteria

1. THE Preprocessing_Pipeline SHALL log at INFO level the start time, end time, and duration (in seconds with 2 decimal places) of each stage (normalize, quality, dynamodb-load, vector-load) per city
2. WHEN a DynamoDB write fails, THE Preprocessing_Pipeline SHALL log at ERROR level the failed PK, SK, error type, and error message
3. WHEN a Bedrock embedding call fails, THE Preprocessing_Pipeline SHALL log at ERROR level the affected entity_id, error type, and error message
4. IF a Source_JSON file cannot be parsed as valid JSON, THEN THE Preprocessing_Pipeline SHALL log at ERROR level the file path, skip the city, and continue with remaining cities
5. THE Preprocessing_Pipeline SHALL produce a final execution summary to stdout containing: total cities processed, total records normalized, DynamoDB items written, vectors uploaded, per-city failure count, per-record failure count by stage, and total execution time
6. WHEN the --verbose flag is specified, THE Preprocessing_Pipeline SHALL output at DEBUG level per-record processing details including source fields mapped, target fields produced, and quality gate result with pass/fail reason
7. THE Preprocessing_Pipeline SHALL use log levels consistently: DEBUG for per-record details, INFO for stage progress and timing, WARNING for recoverable issues (skipped records, missing optional fields), ERROR for failures requiring attention

### Requirement 10: 방문자 통계 정규화

**User Story:** As a data engineer, I want visitor statistics to be properly normalized and loaded into DynamoDB, so that temporal visitor data is queryable alongside city and attraction data.

#### Acceptance Criteria

1. WHEN a Source_JSON contains visitor_statistics data, THE Normalizer SHALL produce monthly records with SK=`STAT#{YYYYMM}` format
2. THE Normalizer SHALL include in each visitor statistics record: city_id, city_name_ko, city_name_en, province, month, year, days, foreigners_daily_avg, foreigners_total, locals_daily_avg, locals_total, out_of_town_daily_avg, out_of_town_total, total_daily_avg, total_visitors
3. THE Normalizer SHALL compute annual_totals and annual_daily_averages aggregates across all months for the same year and include them in each monthly record
4. WHEN visitor statistics contain negative values or non-numeric data, THE Quality_Gate SHALL mark the record quality_status as "failed" with review reason "invalid_statistics_value"
5. THE Vector_Loader SHALL exclude visitor_statistics entity_type records from embedding generation and S3 Vector Store loading
