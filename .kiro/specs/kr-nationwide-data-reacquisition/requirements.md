# Requirements Document

## Introduction

This feature extends the existing South Korea city data acquisition pipeline from a limited scope (강원·경북 only, 18 cities from Wikipedia, 40 cities from DataLab) to cover ALL municipalities (approximately 226 시·군·구) across all 17 Korean metropolitan cities and provinces nationwide. Two data sources are used: Korean Wikipedia (ko.wikipedia.org) for city metadata, and the TourAPI DataLabService (locgoRegnVisitrDDList) for monthly visitor statistics per municipality.

The existing crawling infrastructure in `crawling/KR/` (Wikipedia client, pipeline, normalizer, provinces, target files) and the DataLab script (`.cache/tour_api_korea_repo/scripts/scrape_and_aggregate_visitor.py`) are reused and extended to achieve full national coverage.

This Spec also absorbs the former `kr-tourapi-unique-city-key-reacquisition` bugfix Spec. The existing nationwide Spec remains the single active Kiro Spec for nationwide Korean reacquisition, while the TourAPI unique city key work is represented as additional requirements, design properties, and implementation tasks in this document set.

## Glossary

- **Wikipedia_Crawler**: The existing Python module (`crawling/KR/`) that fetches Korean Wikipedia HTML pages, parses city metadata (description, geography, climate, coordinates, site URLs), and outputs structured CityRecord and PrefectureRecord JSON files
- **DataLab_Collector**: The script that queries the TourAPI DataLabService locgoRegnVisitrDDList endpoint to collect daily visitor counts per signguCode and aggregates them into monthly statistics
- **TourAPI_Detail_Collector**: The KorService2 list/detail acquisition path that creates raw city detail JSON files for attractions and festivals
- **Municipality**: A Korean local government administrative unit (시, 군, or 구) that serves as the atomic geographic entity for data collection
- **Province**: One of the 17 top-level Korean administrative divisions (특별시, 광역시, 특별자치시, 도, 특별자치도), identified by ISO 3166-2:KR codes (KR-11 through KR-50)
- **Target_File**: A JSON file in `crawling/KR/targets/` containing a list of Korean Wikipedia article titles for municipalities belonging to a specific province
- **CityRecord**: The normalized data structure containing city_name_ko, city_name_en, prefecture_id, location, latitude, longitude, description, geography_description, climate_table, and site_urls
- **signguCode**: The numeric code used by the DataLabService API to identify a specific municipality for visitor statistics queries
- **MUNICIPALITY_EN_MAP**: The dictionary in `crawling/KR/provinces.py` mapping Korean municipality names (with disambiguation suffixes) to uppercase English romanizations
- **Pipeline_Orchestrator**: The `pipeline.py` module that coordinates target loading, page fetching, normalization, and JSON output writing with incremental merge support
- **동명이구**: `중구`, `동구`, `서구`, `남구`, `북구`, `강서구`, `고성군`처럼 여러 광역시에 존재하는 같은 시군구명
- **고유 도시 키**: 파일명, S3 key, 전처리 식별자에 사용할 충돌 없는 도시 식별자. 우선순위는 `city_id`, 없으면 `KR-LDONG-{lDongRegnCd}-{lDongSignguCd}`
- **표시명**: 사용자 또는 검색에 표시할 `city_name_ko`, `city_name_en`. 저장 경로의 유일 키로 사용하지 않는다
- **파일 헤더**: Python 파일 상단 모듈 docstring. TourAPI 보정 작업에서는 한국어 설명으로 전환하며, 적용 전 사용자 검토를 받는다
- **파일 이력**: Python 파일 하단의 `# 파일 이력` 주석 블록

## Requirements

### Requirement 1: Nationwide Wikipedia Target Coverage

**User Story:** As a data engineer, I want target files for all 17 Korean provinces, so that the Wikipedia_Crawler can acquire metadata for every municipality nationwide.

#### Acceptance Criteria

1. THE Pipeline_Orchestrator SHALL support loading Target_Files for all 17 provinces defined in the PROVINCES tuple (KR-11 Seoul through KR-50 Jeju)
2. WHEN a Target_File is loaded, THE Pipeline_Orchestrator SHALL associate each municipality title with the correct province prefecture_id
3. THE Target_Files SHALL collectively contain Wikipedia article titles for all municipalities registered in MUNICIPALITY_EN_MAP (approximately 226 entries)
4. WHEN a municipality title includes a disambiguation suffix (e.g., "중구 (서울특별시)"), THE Target_File SHALL preserve the exact disambiguation format matching the MUNICIPALITY_EN_MAP key

### Requirement 2: Province-Level Batch Execution

**User Story:** As a data engineer, I want to run Wikipedia acquisition per province or for all provinces at once, so that I can control execution granularity and recover from partial failures.

#### Acceptance Criteria

1. WHEN the user specifies a single Target_File via --input, THE Wikipedia_Crawler SHALL process only the municipalities in that file
2. WHEN the user specifies a --province-id argument (e.g., KR-11), THE Wikipedia_Crawler SHALL automatically locate and load the corresponding Target_File for that province
3. WHEN the user specifies --all-provinces, THE Wikipedia_Crawler SHALL iterate through all 17 province Target_Files in sequence
4. WHILE processing multiple provinces, THE Wikipedia_Crawler SHALL merge newly acquired CityRecords into the existing cities.json without overwriting previously collected data from other provinces
5. IF the Wikipedia_Crawler encounters a network failure mid-province, THEN THE Wikipedia_Crawler SHALL log the failure, preserve all successfully collected records, and report the incomplete municipalities for retry

### Requirement 3: Nationwide MUNICIPALITY_EN_MAP Completeness

**User Story:** As a data engineer, I want every Korean municipality to have a valid English name mapping, so that city_id generation and CityRecord normalization produce consistent identifiers.

#### Acceptance Criteria

1. THE MUNICIPALITY_EN_MAP SHALL contain entries for all municipalities across all 17 provinces
2. WHEN a municipality name appears in multiple provinces (e.g., "중구", "동구", "남구", "북구", "서구", "강서구", "고성군"), THE MUNICIPALITY_EN_MAP SHALL use a disambiguation key matching the Wikipedia title format (e.g., "중구 (서울특별시)": "JUNG-SEOUL")
3. THE MUNICIPALITY_EN_MAP values SHALL follow the uppercase English romanization convention with province suffix for disambiguation (e.g., "JUNG-SEOUL", "DONG-BUSAN", "GOSEONG-GANGWON")
4. WHEN a new municipality is added to MUNICIPALITY_EN_MAP, THE normalizer SHALL generate a city_id in the format "{prefecture_id}-{ENGLISH_NAME}" (e.g., "KR-11-JONGNO")

### Requirement 4: Wikipedia Data Quality for Nationwide Scope

**User Story:** As a data engineer, I want the Wikipedia_Crawler to produce high-quality CityRecords for all municipalities, so that the downstream pipeline has reliable metadata.

#### Acceptance Criteria

1. WHEN the Wikipedia_Crawler processes a municipality page, THE normalizer SHALL extract at minimum: city_name_ko, prefecture_id, location, and description
2. WHEN a Wikipedia page lacks coordinates, THE normalizer SHALL fall back to Nominatim geocoding using the municipality name and province name as address
3. WHEN a Wikipedia page lacks a climate table, THE normalizer SHALL set the climate_table field to the manual-required placeholder with status STATUS_NEEDS_REVIEW
4. THE Wikipedia_Crawler SHALL populate the field_status dictionary for each CityRecord indicating STATUS_COLLECTED, STATUS_MISSING, or STATUS_NEEDS_REVIEW per field
5. WHEN the Wikipedia_Crawler completes a nationwide run, THE output cities.json SHALL contain one CityRecord per municipality with data_confidence of "medium" or "high" for entries with valid coordinates and province detection
6. WHEN a target title resolves to a Korean Wikipedia disambiguation page, THE Wikipedia_Crawler SHALL mark the municipality as invalid for automatic acceptance and require a corrected target title before the record is considered complete
7. WHEN a municipality has an empty list or empty object for an optional collected field such as site_urls, THE normalizer SHALL mark that field as STATUS_MISSING instead of STATUS_COLLECTED
8. WHEN a municipality lacks latitude or longitude after Wikipedia extraction and Nominatim fallback, THE output SHALL preserve the record but mark coordinates as STATUS_MISSING and include the city in the quality remediation report

### Requirement 5: DataLab signguCode Mapping for All Municipalities

**User Story:** As a data engineer, I want a complete mapping of signguCode values for all Korean municipalities, so that the DataLab_Collector can query visitor statistics for every city nationwide.

#### Acceptance Criteria

1. THE DataLab_Collector SHALL maintain a signguCode lookup covering all municipalities across all 17 provinces
2. WHEN the signguCode mapping is loaded, THE DataLab_Collector SHALL validate that each code is a numeric string of consistent length
3. THE signguCode mapping SHALL associate each code with both city_name_ko and city_name_en for cross-referencing with CityRecords
4. IF a municipality does not have a known signguCode, THEN THE DataLab_Collector SHALL log a warning and skip that municipality without terminating the collection run

### Requirement 6: Nationwide Visitor Statistics Collection

**User Story:** As a data engineer, I want to collect monthly visitor statistics for all municipalities nationwide, so that the downstream pipeline has complete visitor data for crowding analysis.

#### Acceptance Criteria

1. WHEN the DataLab_Collector executes a nationwide run, THE DataLab_Collector SHALL query the locgoRegnVisitrDDList endpoint for each month in the target year (12 months)
2. WHEN API responses are received, THE DataLab_Collector SHALL filter records by signguCode against the nationwide signguCode mapping
3. THE DataLab_Collector SHALL aggregate daily records into monthly totals per municipality for each touDivCd (1=locals, 2=out_of_town, 3=foreigners)
4. THE DataLab_Collector SHALL compute monthly daily averages by dividing monthly totals by the number of days in each month
5. WHEN the DataLab_Collector completes a nationwide run, THE output SHALL contain visitor_statistics for each municipality with annual_totals, annual_daily_averages, and monthly_statistics arrays

### Requirement 7: API Key Rotation and Rate Limiting

**User Story:** As a data engineer, I want robust API key management during nationwide collection, so that large-volume requests complete without manual intervention.

#### Acceptance Criteria

1. WHEN the DataLab_Collector receives an HTTP 429 or quota-exceeded error (code 22/0022), THE DataLab_Collector SHALL rotate to the next available API key
2. WHILE all API keys are exhausted, THE DataLab_Collector SHALL terminate the run with a clear error message indicating key exhaustion
3. THE DataLab_Collector SHALL enforce a minimum delay between consecutive API requests to respect rate limits
4. WHEN a transient network error occurs, THE DataLab_Collector SHALL retry up to 3 times with exponential backoff before marking the request as failed
5. THE DataLab_Collector SHALL support loading multiple API keys from the environment configuration for key pool rotation

### Requirement 8: Output Integration and Merge Strategy

**User Story:** As a data engineer, I want Wikipedia metadata and visitor statistics to be stored in a consistent structure, so that the downstream data pipeline can consume them uniformly.

#### Acceptance Criteria

1. THE Wikipedia_Crawler SHALL output nationwide results to data/KR/cities.json and data/KR/prefectures.json with incremental merge (new records added, existing records updated)
2. THE DataLab_Collector SHALL output visitor statistics to a structured JSON file keyed by city_name_en with monthly_statistics arrays
3. WHEN both data sources are collected, THE pipeline SHALL support a merge step that embeds visitor_statistics into the corresponding city's final output file
4. THE merged output SHALL preserve the existing data contract structure (city metadata + visitor_statistics) used by the downstream ELT pipeline
5. IF a municipality has Wikipedia metadata but no visitor statistics (or vice versa), THEN THE pipeline SHALL preserve whichever data is available and mark the missing source as incomplete

### Requirement 9: Incremental and Resumable Collection

**User Story:** As a data engineer, I want to resume a partially completed nationwide collection, so that I do not re-collect already acquired data after interruptions.

#### Acceptance Criteria

1. WHEN the Wikipedia_Crawler starts, THE Pipeline_Orchestrator SHALL load existing cities.json and merge new results without discarding previously collected records
2. WHEN the DataLab_Collector starts, THE DataLab_Collector SHALL check which municipalities already have complete visitor_statistics and skip them unless --force-refresh is specified
3. THE Wikipedia_Crawler SHALL log collection progress including the count of newly acquired cities, skipped cities (already collected), and failed cities per province
4. IF a collection run is interrupted, THEN THE pipeline SHALL persist all successfully collected records to disk before terminating

### Requirement 10: S3 Upload for Nationwide Results

**User Story:** As a data engineer, I want to upload the complete nationwide dataset to S3, so that the downstream ELT pipeline can consume it from the canonical data store.

#### Acceptance Criteria

1. WHEN --upload-to-s3 is specified, THE Wikipedia_Crawler SHALL upload cities.json and prefectures.json to the configured S3 bucket with the ingest date prefix
2. THE S3 uploader SHALL use checksum-based deduplication to skip upload when the file content matches the existing S3 object
3. WHEN the nationwide dataset exceeds the previous scope (approximately 226 vs 18 cities), THE S3 uploader SHALL handle the larger file size without timeout errors
4. THE S3 upload key pattern SHALL follow: raw/KR/wikipedia/{YYYYMMDD}/cities.json and raw/KR/wikipedia/{YYYYMMDD}/prefectures.json

### Requirement 11: Wikipedia Nationwide Quality Remediation

**User Story:** As a data engineer, I want known quality gaps from the nationwide Wikipedia review to be represented in the Spec, so that follow-up work fixes the actual weak points instead of only checking record counts.

#### Acceptance Criteria

1. THE target files SHALL correct known disambiguation-page targets identified in the 2026-06-29 review: `광주시` and `영광군`
2. WHEN target title corrections are made, THE corresponding `MUNICIPALITY_EN_MAP` keys SHALL remain aligned with the target titles
3. THE pipeline SHALL include verification that flags descriptions matching Korean disambiguation-page patterns such as `다른 뜻은 다음과 같다` or `다음 등을 가리킨다`
4. THE pipeline SHALL include a remediation path for the 9 municipalities with missing coordinates identified in the 2026-06-29 review
5. THE normalizer SHALL treat empty containers as missing field values for field_status purposes
6. THE test suite SHALL cover `--province-id`, `--all-provinces`, `acquire_province()`, and `acquire_all_provinces()` behavior
7. THE completion report SHALL distinguish nationwide coverage completeness from Wikipedia content-quality completeness

### Requirement 12: TourAPI Storage Key Uniqueness

**User Story:** 데이터 엔지니어로서, 동명이구 TourAPI 결과가 서로 다른 파일로 저장되기를 원한다. 그래야 전국 재취득 시 스킵 또는 덮어쓰기 없이 모든 도시를 보존할 수 있다.

#### Acceptance Criteria

1. THE TourAPI_Detail_Collector SHALL NOT generate output file names from standalone `city_name_en`
2. THE TourAPI_Detail_Collector SHALL use `meta.city_id` as the storage key when available, and SHALL fall back to `KR-LDONG-{lDongRegnCd}-{lDongSignguCd}` when `city_id` is unavailable
3. WHEN the target municipality is one of `중구`, `동구`, `서구`, `남구`, `북구`, `강서구`, or `고성군`, THE output paths SHALL remain distinct by province
4. THE collector SHALL preserve `city_name_ko` and `city_name_en` as display/search metadata
5. THE detail cache SHALL be used only for content detail reuse and SHALL NOT cause city output path collisions

### Requirement 13: Province-Aware TourAPI City Mapping

**User Story:** 데이터 엔지니어로서, TourAPI legal-dong target을 `cities.json`의 disambiguated 도시 레코드와 정확히 매핑하고 싶다. 그래야 `중구` 같은 단독명이 올바른 `JUNG-SEOUL`, `JUNG-ULSAN` 등으로 연결된다.

#### Acceptance Criteria

1. THE TourAPI city lookup SHALL NOT use standalone `city_name_ko` as a unique key
2. THE lookup SHALL match by administrative code when available, otherwise by `(province, city_name_ko)`
3. THE lookup SHALL preserve `city_id`, `city_name_en`, and `prefecture_id` from `data/KR/cities.json` in TourAPI raw metadata
4. WHEN lookup fails, THE fallback SHALL create a unique code-based city key
5. THE pipeline SHALL include lookup failures in validation output instead of silently ignoring them

### Requirement 14: DataLab Visitor Statistics Association for TourAPI Details

**User Story:** 데이터 엔지니어로서, TourAPI detail raw에 포함되는 방문통계가 동명이구에 잘못 붙지 않기를 원한다. 그래야 raw/detail과 V2 visitor_statistics가 같은 도시 기준을 공유한다.

#### Acceptance Criteria

1. THE `collect_city_detail()` flow SHALL NOT identify a city by standalone `lDongSignguCd` only
2. THE DataLab mapping used by TourAPI detail collection SHALL include province or official signguCode context
3. THE visitor statistics embedded in raw detail output SHALL preserve `city_id`, `city_name_en`, province, and source code metadata
4. WHEN visitor statistics are unavailable, THE TourAPI raw/detail generation SHALL continue and SHALL report the missing statistics as a validation item

### Requirement 15: TourAPI S3 Raw Key and Manifest Uniqueness

**User Story:** 운영자로서, S3 raw 객체가 도시별로 충돌 없이 업로드되기를 원한다. 그래야 새 ingest date의 raw prefix를 신뢰할 수 있다.

#### Acceptance Criteria

1. THE `src/kr_details_pipeline/s3_keys.py` module SHALL support raw detail key generation from a unique city key
2. THE raw manifest builder SHALL read the unique city key from raw file metadata when creating S3 keys
3. THE manifest SHALL preserve `city_key`, `city_id`, `city_name_en`, `city_name_ko`, province, `lDongRegnCd`, and `lDongSignguCd`
4. THE S3 raw keys for the known homonymous municipality set SHALL have zero duplicates
5. THE corrected upload SHALL use a new ingest date and SHALL NOT overwrite the existing `20260625` raw prefix in place

### Requirement 16: Transform and DynamoDB V2 Key Alignment

**User Story:** 서비스 데이터 소비자로서, DynamoDB V2에서 동명이구가 같은 `CITY#JUNG-GU` 같은 키로 합쳐지지 않기를 원한다.

#### Acceptance Criteria

1. THE raw transform and domain preprocess SHALL be able to use the unique city key as the city partition key candidate
2. THE V2 load path SHALL NOT use standalone `city_name_en` as the partition key for homonymous municipalities
3. THE `city_metadata`, `attraction`, `festival`, and `visitor_statistics` records SHALL share the same city key
4. THE load candidate or dry-run validation output SHALL show zero partition key duplicates for homonymous municipalities

### Requirement 17: Korean File Headers and File History

**User Story:** 유지보수자로서, 수정된 파일의 목적과 이력을 한국어로 빠르게 이해하고 싶다.

#### Acceptance Criteria

1. THE modified Python modules SHALL use Korean module docstrings as file headers
2. BEFORE applying file headers to Python files, THE agent SHALL present the header text to the user for review
3. THE modified Python modules and tests SHALL include or update a `# 파일 이력` block at the bottom of the file
4. THE file history SHALL include date, reason, and worker at the end of the sentence in `(github name)` format
5. THE header/history rule SHALL apply to test files when those files are modified

### Requirement 18: TourAPI Verification and Safe Reacquisition Procedure

**User Story:** 운영자로서, 전체 재취득 전에 동명이구 smoke 검증을 먼저 보고 싶다. 그래야 대량 API 호출 전에 키 보정이 실제로 동작하는지 확인할 수 있다.

#### Acceptance Criteria

1. THE unit test suite SHALL verify that known homonymous municipality targets have distinct output paths and S3 keys
2. THE smoke reacquisition set SHALL include at least 서울 중구, 울산 중구, 강원 고성군, and 경남 고성군
3. THE smoke report SHALL include raw/detail file count, metadata alignment, and visitor statistics association status
4. THE nationwide reacquisition SHALL run only after smoke validation, using a new ingest date
5. THE completion report SHALL distinguish existing `20260625` outputs from the new ingest date outputs

## Current Review Findings

The 2026-06-29 review found that nationwide coverage is complete by count but content quality still needs remediation.

- Target files: 17
- Target total: 229
- `MUNICIPALITY_EN_MAP`: 229
- `data/KR/cities.json`: 229
- `data/KR/prefectures.json`: 17
- `city_id` duplicates: 0
- `city_name_en` duplicates: 0
- Known disambiguation-page records: `KR-41-GWANGJU-GYEONGGI`, `KR-46-YEONGGWANG`
- Missing coordinate records: 9
- Empty `site_urls` marked as collected: 5
- Existing direct test coverage gap: province/all-provinces execution path

## Change History

- 2026-06-29: Added Wikipedia nationwide quality remediation requirements from `docs/reports/kr_wikipedia_nationwide_acquisition_review_20260629.md`.
- 2026-06-29: Merged `kr-tourapi-unique-city-key-reacquisition` requirements into this existing nationwide Spec and kept this Spec as the single active Kiro Spec for KR reacquisition.
