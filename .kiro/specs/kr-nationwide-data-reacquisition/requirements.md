# Requirements Document

## Introduction

This feature extends the existing South Korea city data acquisition pipeline from a limited scope (강원·경북 only, 18 cities from Wikipedia, 40 cities from DataLab) to cover ALL municipalities (approximately 226 시·군·구) across all 17 Korean metropolitan cities and provinces nationwide. Two data sources are used: Korean Wikipedia (ko.wikipedia.org) for city metadata, and the TourAPI DataLabService (locgoRegnVisitrDDList) for monthly visitor statistics per municipality.

The existing crawling infrastructure in `crawling/KR/` (Wikipedia client, pipeline, normalizer, provinces, target files) and the DataLab script (`.cache/tour_api_korea_repo/scripts/scrape_and_aggregate_visitor.py`) are reused and extended to achieve full national coverage.

## Glossary

- **Wikipedia_Crawler**: The existing Python module (`crawling/KR/`) that fetches Korean Wikipedia HTML pages, parses city metadata (description, geography, climate, coordinates, site URLs), and outputs structured CityRecord and PrefectureRecord JSON files
- **DataLab_Collector**: The script that queries the TourAPI DataLabService locgoRegnVisitrDDList endpoint to collect daily visitor counts per signguCode and aggregates them into monthly statistics
- **Municipality**: A Korean local government administrative unit (시, 군, or 구) that serves as the atomic geographic entity for data collection
- **Province**: One of the 17 top-level Korean administrative divisions (특별시, 광역시, 특별자치시, 도, 특별자치도), identified by ISO 3166-2:KR codes (KR-11 through KR-50)
- **Target_File**: A JSON file in `crawling/KR/targets/` containing a list of Korean Wikipedia article titles for municipalities belonging to a specific province
- **CityRecord**: The normalized data structure containing city_name_ko, city_name_en, prefecture_id, location, latitude, longitude, description, geography_description, climate_table, and site_urls
- **signguCode**: The numeric code used by the DataLabService API to identify a specific municipality for visitor statistics queries
- **MUNICIPALITY_EN_MAP**: The dictionary in `crawling/KR/provinces.py` mapping Korean municipality names (with disambiguation suffixes) to uppercase English romanizations
- **Pipeline_Orchestrator**: The `pipeline.py` module that coordinates target loading, page fetching, normalization, and JSON output writing with incremental merge support

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
