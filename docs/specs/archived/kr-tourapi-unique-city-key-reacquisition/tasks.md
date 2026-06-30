# Implementation Plan: KR TourAPI 고유 도시 키 기반 재취득 보정

## Overview

이 Plan은 동명이구 TourAPI raw/detail 스킵/덮어쓰기 문제를 고치고, 새 ingest date로 안전하게 재취득할 수 있는 라인을 만든다. 모든 구현 Task는 Sequential Mode로 진행한다. 파일 헤더 문안은 사용자 승인 전까지 코드에 적용하지 않는다.

## Tasks

- [ ] 0. Header approval gate
  - [ ] 0.1 사용자에게 수정 대상 파일별 한국어 파일 헤더 문안을 제시하고 승인받기
    - 대상: `crawling/KR/tour_api_region_detail_acquisition.py`, `crawling/KR/tour_api_city_detail_acquisition.py`, `crawling/KR/datalab_collector.py`, `src/kr_details_pipeline/s3_keys.py`, `src/kr_details_pipeline/manifest.py`, `src/kr_details_pipeline/transform.py`, 관련 테스트 파일
    - 승인 전 Python 파일의 모듈 docstring을 수정하지 않는다.
    - _Requirements: 6.1, 6.2_

- [ ] 1. City identity and TourAPI output key 보정
  - [ ] 1.1 Province-aware city identity helper 추가
    - Purpose: TourAPI target을 `cities.json`의 disambiguated 도시와 정확히 연결한다.
    - Scope: `crawling/KR/tour_api_region_detail_acquisition.py`
    - Acceptance: 동명이구 29개 대상의 `city_key`가 모두 고유하다.
    - Verification: 관련 단위 테스트와 identity 중복 검사
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3_

  - [ ] 1.2 TourAPI list/detail output path를 `city_key` 기반으로 변경
    - Purpose: `jung-gu.json`, `dong-gu.json` 같은 단독 파일명 충돌을 제거한다.
    - Scope: `tour_api_region_detail_acquisition.py`, `tour_api_city_detail_acquisition.py`
    - Acceptance: `output_path`와 `list_path`가 `city_name_en` 단독 값을 사용하지 않는다.
    - Verification: 서울/울산 중구, 강원/경남 고성군 테스트
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 1.3 전국 대상 옵션을 재현 가능한 CLI로 정리
    - Purpose: 임시 `_run_nationwide.py` 없이 전국 재취득을 반복 실행 가능하게 한다.
    - Scope: `tour_api_region_detail_acquisition.py`
    - Acceptance: 전국 target 파일 또는 region option을 명시적으로 선택할 수 있다.
    - Verification: dry-run 또는 limit 기반 smoke 실행
    - _Requirements: 7.4_

- [ ] 2. DataLab 방문통계 결합 보정
  - [ ] 2.1 단일 도시 방문통계 수집에 city identity 전달
    - Purpose: raw/detail 내부 visitor_statistics가 동명이구에 잘못 붙는 것을 막는다.
    - Scope: `tour_api_city_detail_acquisition.py`, `datalab_collector.py`
    - Acceptance: 방문통계 결과에 city identity 추적 필드가 남는다.
    - Verification: mocked DataLab 응답 단위 테스트
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 3. S3 raw manifest와 key 고유화
  - [ ] 3.1 manifest record에 `city_key`와 행정코드 필드 추가
    - Purpose: S3 raw 업로드 결과에서 도시 식별자를 추적 가능하게 한다.
    - Scope: `src/kr_details_pipeline/manifest.py`
    - Acceptance: raw manifest가 `city_key`, `city_id`, `lDongRegnCd`, `lDongSignguCd`를 포함한다.
    - Verification: `test_manifest.py`
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 3.2 S3 raw key 중복 방지 테스트 추가
    - Purpose: 동명이구가 S3에서 같은 key로 수렴하지 않음을 보장한다.
    - Scope: `src/kr_details_pipeline/s3_keys.py`, `test_s3_keys.py`
    - Acceptance: 동명이구 29개 대상의 S3 key 중복이 0건이다.
    - Verification: `uv run pytest src/kr_details_pipeline/tests/test_s3_keys.py src/kr_details_pipeline/tests/test_manifest.py`
    - _Requirements: 4.4, 4.5_

- [ ] 4. Transform/DynamoDB V2 key 정합성 보정
  - [ ] 4.1 transform city record에 `city_key` 보존
    - Purpose: 후단 load candidate가 `city_name_en` 단독 PK로 수렴하지 않게 한다.
    - Scope: `src/kr_details_pipeline/transform.py`
    - Acceptance: transformed records가 city key와 표시명을 모두 가진다.
    - Verification: `test_transform.py`
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 4.2 load candidate 또는 dry-run에서 동명이구 PK 중복 검사 추가
    - Purpose: DynamoDB V2 적재 전 키 충돌을 차단한다.
    - Scope: 필요 시 `load.py`, `domain_preprocess.py`, 테스트 파일
    - Acceptance: 동명이구 PK 중복이 있으면 검증 실패로 보고된다.
    - Verification: 단위 테스트 또는 dry-run 출력 검사
    - _Requirements: 5.4_

- [ ] 5. 한국어 파일 헤더와 파일 이력 적용
  - [ ] 5.1 승인된 한국어 파일 헤더 적용
    - Purpose: 수정 파일의 책임을 한국어로 명확히 한다.
    - Scope: 승인된 대상 파일만
    - Acceptance: 승인받은 문안과 코드 헤더가 일치한다.
    - Verification: 대상 파일 header grep
    - _Requirements: 6.1, 6.2_

  - [ ] 5.2 파일 이력 작성
    - Purpose: 변경 사유를 파일 안에 남긴다.
    - Scope: 수정된 Python 파일과 테스트 파일
    - Acceptance: 각 수정 파일 하단에 `# 파일 이력`과 2026-06-29 변경 이력이 있고, 이력 문장 끝에 작업자를 `(github name)` 형식으로 표기한다.
    - Verification: `rg -n "파일 이력|2026-06-29" <target-files>`
    - _Requirements: 6.3, 6.4, 6.5_

- [ ] 6. Verification and reacquisition readiness report
  - [ ] 6.1 관련 단위 테스트 실행
    - Command: `uv run pytest crawling/KR/tests/test_tour_api_region_detail_acquisition.py crawling/KR/tests/test_tour_api_city_detail_acquisition.py src/kr_details_pipeline/tests/test_s3_keys.py src/kr_details_pipeline/tests/test_manifest.py src/kr_details_pipeline/tests/test_transform.py`
    - Acceptance: 관련 테스트가 통과하거나 실패 원인이 보고된다.
    - _Requirements: 7.1_

  - [ ] 6.2 smoke 재취득 절차와 결과 보고
    - Purpose: 전국 재취득 전 동명이구 핵심 케이스를 검증한다.
    - Scope: 서울 중구, 울산 중구, 강원 고성군, 경남 고성군
    - Acceptance: 각 대상이 별도 raw/detail 파일로 생성되고 meta가 일치한다.
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

## Change History

- 2026-06-29: 파일 헤더 승인 게이트, 고유 도시 키 보정, S3/DynamoDB 정합성 검증 Task를 추가했다. (github name)
