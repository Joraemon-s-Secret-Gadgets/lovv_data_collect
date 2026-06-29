# Requirements Document: KR TourAPI 고유 도시 키 기반 재취득 보정

## Introduction

KR TourAPI KorService2 관광지/축제 상세 취득과 DataLab 방문통계 결합 과정에서 `city_name_en` 또는 단독 시군구명이 저장 키로 사용되어 동명이구 데이터가 스킵 또는 덮어쓰기 되는 문제가 확인되었다. 이 Spec은 TourAPI raw/detail 생성, S3 raw key, 전처리/DynamoDB 적재 후보가 모두 고유 도시 키를 사용하도록 보정하고, 새 ingest date로 재취득할 수 있는 실행 라인을 만든다.

본 작업은 기존 `kr-nationwide-data-reacquisition` Spec의 전국 취득 범위를 대체하지 않고, 그 취득 결과의 키 충돌 결함을 보정하는 bugfix Spec이다.

## Glossary

- **동명이구**: `중구`, `동구`, `서구`, `남구`, `북구`, `강서구`, `고성군`처럼 여러 광역시에 존재하는 같은 시군구명.
- **고유 도시 키**: 파일명, S3 key, 전처리 식별자에 사용할 충돌 없는 도시 식별자. 우선순위는 `city_id`, 없으면 `KR-LDONG-{lDongRegnCd}-{lDongSignguCd}`.
- **표시명**: 사용자 또는 검색에 표시할 `city_name_ko`, `city_name_en`. 저장 경로의 유일 키로 사용하지 않는다.
- **재취득 라인**: TourAPI list/detail 취득, DataLab 방문통계 결합, S3 raw 업로드, processed domain 생성, DynamoDB V2 적재 검증까지 이어지는 실행 흐름.
- **파일 헤더**: Python 파일 상단 모듈 docstring. 이번 작업에서는 한국어 설명으로 전환하며, 적용 전 사용자 검토를 받는다.
- **파일 이력**: Python 파일 하단의 `# 파일 이력` 주석 블록.

## Requirements

### Requirement 1: TourAPI 저장 키 고유화

**User Story:** 데이터 엔지니어로서, 동명이구 TourAPI 결과가 서로 다른 파일로 저장되기를 원한다. 그래야 전국 재취득 시 스킵 또는 덮어쓰기 없이 모든 도시를 보존할 수 있다.

#### Acceptance Criteria

1. TourAPI region/detail 취득은 output 파일명을 `city_name_en` 단독으로 생성하지 않는다.
2. 저장 키는 `meta.city_id`가 있으면 이를 사용하고, 없으면 `KR-LDONG-{lDongRegnCd}-{lDongSignguCd}`를 사용한다.
3. `중구`, `동구`, `서구`, `남구`, `북구`, `강서구`, `고성군` 대상은 각각 별도 output path를 가진다.
4. 기존 `city_name_en`은 표시/검색용 메타데이터로 보존된다.
5. 기존 detail cache는 콘텐츠 상세 cache로만 사용하고, 도시 output path 충돌을 일으키지 않는다.

### Requirement 2: Province-aware city mapping

**User Story:** 데이터 엔지니어로서, TourAPI legal-dong target을 `cities.json`의 disambiguated 도시 레코드와 정확히 매핑하고 싶다. 그래야 `중구` 같은 단독명이 올바른 `JUNG-SEOUL`, `JUNG-ULSAN` 등으로 연결된다.

#### Acceptance Criteria

1. city lookup은 `city_name_ko` 단독 키를 사용하지 않는다.
2. lookup은 행정코드 또는 `(province, city_name_ko)` 기준으로 수행한다.
3. `data/KR/cities.json`의 `city_id`, `city_name_en`, `prefecture_id`를 TourAPI meta에 보존한다.
4. lookup 실패 시 fallback은 고유 도시 키를 만들 수 있는 코드 기반 정보를 사용한다.
5. lookup 실패는 조용히 무시하지 않고 검증 보고에 포함한다.

### Requirement 3: DataLab 방문통계 결합 보정

**User Story:** 데이터 엔지니어로서, TourAPI detail raw에 포함되는 방문통계가 동명이구에 잘못 붙지 않기를 원한다. 그래야 raw/detail과 V2 visitor_statistics가 같은 도시 기준을 공유한다.

#### Acceptance Criteria

1. `collect_city_detail()` 내부 DataLab 호출은 단독 `lDongSignguCd`만으로 도시를 확정하지 않는다.
2. DataLab 매핑은 province 또는 공식 signguCode 매핑을 함께 사용한다.
3. 방문통계 결과에는 `city_id`, `city_name_en`, `province`, 기준 코드가 추적 가능하게 남는다.
4. 방문통계가 없는 도시는 raw/detail 생성을 실패시키지 않고 경고와 검증 대상에 남긴다.

### Requirement 4: S3 raw key와 manifest 고유화

**User Story:** 운영자로서, S3 raw 객체가 도시별로 충돌 없이 업로드되기를 원한다. 그래야 새 ingest date의 raw prefix를 신뢰할 수 있다.

#### Acceptance Criteria

1. `src/kr_details_pipeline/s3_keys.py`는 raw detail key 생성 시 고유 도시 키를 지원한다.
2. `build_raw_manifest()`는 raw file meta에서 고유 도시 키를 읽어 S3 key를 만든다.
3. manifest에는 `city_key`, `city_id`, `city_name_en`, `city_name_ko`, `province`, `lDongRegnCd`, `lDongSignguCd`가 추적 가능하게 남는다.
4. 동명이구 29개 대상의 S3 key는 모두 다르다.
5. 신규 업로드는 기존 `20260625` prefix를 제자리 수정하지 않고 새 ingest date를 사용한다.

### Requirement 5: 전처리와 DynamoDB V2 키 정합성

**User Story:** 서비스 데이터 소비자로서, DynamoDB V2에서 동명이구가 같은 `CITY#JUNG-GU` 같은 키로 합쳐지지 않기를 원한다.

#### Acceptance Criteria

1. raw transform과 domain preprocess는 고유 도시 키를 city partition key 후보로 사용할 수 있다.
2. `city_name_en` 단독 PK 생성은 동명이구에 사용하지 않는다.
3. `city_metadata`, `attraction`, `festival`, `visitor_statistics`가 같은 city key를 공유한다.
4. load candidate 또는 dry-run 결과에서 동명이구 PK 중복이 0건이다.

### Requirement 6: 한국어 파일 헤더와 파일 이력

**User Story:** 유지보수자로서, 수정된 파일의 목적과 이력을 한국어로 빠르게 이해하고 싶다.

#### Acceptance Criteria

1. 수정 대상 Python 파일의 모듈 docstring은 한국어 파일 헤더로 전환한다.
2. 파일 헤더 문안은 코드 적용 전에 사용자 검토를 받는다.
3. 수정 대상 Python 파일 하단에는 `# 파일 이력` 블록을 추가하거나 갱신한다.
4. 파일 이력은 날짜, 변경 사유, 작업자를 한 줄 이상으로 기록하고 작업자는 문장 끝에 `(github name)` 형식으로 표기한다.
5. 테스트 파일도 수정되는 경우 한국어 파일 헤더와 파일 이력을 적용한다.

### Requirement 7: 검증과 재취득 절차

**User Story:** 운영자로서, 전체 재취득 전에 동명이구 smoke 검증을 먼저 보고 싶다. 그래야 대량 API 호출 전에 키 보정이 실제로 동작하는지 확인할 수 있다.

#### Acceptance Criteria

1. 단위 테스트는 동명이구 29개 대상이 서로 다른 output path/S3 key를 갖는지 검증한다.
2. smoke 재취득 대상은 최소 서울 중구, 울산 중구, 강원 고성군, 경남 고성군을 포함한다.
3. smoke 결과는 raw/detail 파일 수, meta 정합성, 방문통계 연결 상태를 보고한다.
4. 전국 재취득은 smoke 검증 후 새 ingest date로 수행한다.
5. 완료 보고서는 기존 `20260625`와 신규 ingest date의 수량 차이를 구분한다.

## Assumptions

1. 이번 작업은 실제 전국 재취득 실행 전에 코드와 검증 라인을 먼저 보정한다.
2. 기존 raw prefix `raw/KR/details/20260625/`는 보존한다.
3. 새 ingest date는 실제 실행일을 사용하되, 문서 예시는 `20260629`를 사용한다.
4. 파일 헤더 문안은 사용자가 승인한 후에만 Python 파일에 반영한다.

## Change History

- 2026-06-29: TourAPI 동명이구 저장 키 충돌 분석 결과를 바탕으로 bugfix Spec을 생성했다. (github name)
