# KR TourAPI 재취득 방안 보고서

- 작성일: 2026-06-29
- 대상: TourAPI KorService2 관광지/축제 상세 raw, DataLab 방문통계 raw 포함 재취득
- 결론: 현재 코드 그대로 재실행하면 동명이구 충돌이 재발하므로, 저장 키 보정 후 새 ingest date로 전체 재취득해야 한다.

## 1. 현재 문제

TourAPI API 호출 자체는 `lDongRegnCd`, `lDongSignguCd`를 사용하므로 지역 조회 범위는 코드 기반이다.

문제는 저장 단계다.

- `crawling/KR/tour_api_region_detail_acquisition.py`
  - `city_name_en = city_name_lookup.get(city_name_ko, ...)`
  - `output_path = data/KR/details/{slugify(city_name_en)}.json`
  - `list_path = data/KR/raw_tour_api/{slugify(city_name_en)}_filtered.json`
- `crawling/KR/tour_api_city_detail_acquisition.py`
  - detail 최종 파일도 `meta.city_name_en` 단독으로 파일명을 만든다.
- `src/kr_details_pipeline/s3_keys.py`
  - S3 raw key도 `raw/KR/details/{ingest_date}/{city_name_en}.json` 형태다.

따라서 `중구`, `동구`, `서구`, `고성군`처럼 같은 시군구명이 여러 광역시에 존재하면 같은 파일명으로 수렴한다.

## 2. 확인된 영향 범위

`ldong_sigungu_nationwide.json` 기준 동명이구 충돌 그룹은 7개, 총 29개 대상이다. 중복으로 사라질 수 있는 초과분은 22개다.

| 시군구명 | 대상 수 | 대상 |
|---|---:|---|
| 강서구 | 2 | 서울, 부산 |
| 고성군 | 2 | 강원특별자치도, 경상남도 |
| 남구 | 4 | 대구, 광주, 부산, 울산 |
| 동구 | 6 | 인천, 대전, 대구, 광주, 부산, 울산 |
| 북구 | 4 | 대구, 광주, 부산, 울산 |
| 서구 | 5 | 인천, 대전, 대구, 광주, 부산 |
| 중구 | 6 | 서울, 인천, 대전, 대구, 부산, 울산 |

현재 로컬 산출물에도 충돌 흔적이 있다.

- `data/KR/details/jung-gu.json`은 울산 중구로 남아 있다.
- `data/KR/details/dong-gu.json`은 울산 동구로 남아 있다.
- `data/KR/details/goseong-gangwon.json`은 파일명과 달리 경상남도 고성군으로 남아 있다.

이는 기존 파일이 있으면 뒤 대상이 `skip existing`되고, overwrite 실행에서는 마지막 대상이 앞 대상 파일을 덮어쓰는 구조다.

## 3. 재취득 원칙

기존 `20260625` 산출물을 제자리 갱신하지 말고, 새 ingest date로 분리한다.

권장 ingest date:

- `20260629` 또는 실제 실행일 `YYYYMMDD`

기존 S3 prefix:

- `raw/KR/details/20260625/`
- `processed/KR/domain/20260625/`

신규 prefix 예:

- `raw/KR/details/20260629/`
- `processed/KR/domain/20260629/`

이렇게 해야 기존 적재분과 신규 보정분을 비교하고 rollback할 수 있다.

## 4. 선행 패치

재취득 전에 다음을 먼저 고쳐야 한다.

### 4.1 TourAPI raw/detail 파일 키

파일명과 S3 key를 `city_name_en` 단독이 아니라 고유 city key로 만든다.

권장 키:

- `city_id`가 있으면 `city_id`
- 없으면 `KR-LDONG-{lDongRegnCd}-{lDongSignguCd}`

예:

- 서울 중구: `KR-LDONG-1-24.json`
- 울산 중구: `KR-LDONG-7-1.json`
- 강원 고성군: `KR-LDONG-32-2.json`
- 경남 고성군: `KR-LDONG-36-3.json`

`city_name_en`은 표시/검색용 값으로 보존하되 저장 경로의 유일 키로 쓰지 않는다.

### 4.2 city name lookup

현재 `_load_city_name_lookup()`은 `city_name_ko` 단독 키다. 이를 다음 중 하나로 바꿔야 한다.

- `lDongRegnCd + lDongSignguCd` 기준 lookup
- 또는 `(province, city_name_ko)` 기준 lookup

`data/KR/cities.json`에는 이미 `중구 (서울특별시)`, `중구 (울산광역시)`처럼 disambiguated 이름과 `JUNG-SEOUL`, `JUNG-ULSAN` 같은 고유 영문명이 있으므로 이를 사용해야 한다.

### 4.3 전국 대상 수집

현재 `tour_api_region_detail_acquisition.py`는 `TARGET_REGION_CODES = {"51", "47"}`로 강원/경북 대상에 묶여 있다.

전국 재취득은 다음 중 하나가 필요하다.

- `--region-code all` 또는 `--region-code` 반복 옵션 추가
- 전국 대상 파일 `ldong_sigungu_nationwide.json`을 읽는 별도 엔트리포인트 추가

임시 `_run_nationwide.py` 방식은 재현성과 검증성이 낮으므로 다시 쓰지 않는 편이 맞다.

### 4.4 DataLab 방문통계

`collect_city_detail()` 내부 방문통계 호출은 현재 `lDongSignguCd`만 `collect_visitor_statistics_for_city()`에 넘긴다.

동명이구 보정 재취득에서는 방문통계도 다음 기준으로 고쳐야 한다.

- DataLab 원천에서 사용하는 공식 `signguCode`를 `lDongRegnCd/lDongSignguCd`와 명확히 매핑
- `city_id`, `city_name_en`, `province`를 함께 보존
- `visitor_statistics` PK/SK 생성은 `city_id` 기반으로 검증

이 패치 없이 방문통계를 함께 재취득하면 TourAPI raw는 고쳐도 방문통계가 다시 잘못 붙을 수 있다.

## 5. 재취득 실행 순서

### Step 1. 코드 패치 및 단위 검증

필수 검증:

- 동명이구 29개 대상이 서로 다른 output path를 갖는지 테스트
- `jung-gu.json`, `dong-gu.json` 같은 단독 파일명이 더 이상 생성되지 않는지 테스트
- S3 raw key가 `city_id` 또는 `KR-LDONG-*` 기반인지 테스트
- DataLab 방문통계가 단독 `lDongSignguCd`가 아니라 고유 매핑을 쓰는지 테스트

권장 테스트:

```powershell
uv run pytest crawling/KR/tests/test_tour_api_region_detail_acquisition.py crawling/KR/tests/test_tour_api_city_detail_acquisition.py src/kr_details_pipeline/tests/test_s3_keys.py src/kr_details_pipeline/tests/test_manifest.py
```

### Step 2. smoke 재취득

동명이구 중 최소 4개를 먼저 재취득한다.

권장 smoke 대상:

- 서울 중구
- 울산 중구
- 강원 고성군
- 경남 고성군

검증 기준:

- raw/detail 파일 4개가 모두 별도 파일로 생성된다.
- 각 파일의 `meta.province`, `meta.city_name_ko`, `meta.city_name_en`, `meta.city_id`가 서로 다르다.
- visitor_statistics가 붙는 경우 12개월 데이터가 해당 city_id에만 붙는다.

### Step 3. 전국 TourAPI 재취득

새 출력 디렉터리를 사용한다.

예:

```powershell
uv run python -m crawling.KR.tour_api_region_detail_acquisition --env-file .env --reference-dir .cache/tour_api_korea_repo/data --cities-json data/KR/cities.json --output-dir data/KR/details_20260629 --work-dir data/KR/raw_tour_api_20260629 --detail-cache-dir data/KR/detail_cache --overwrite
```

주의: 위 명령은 전국 대상 옵션 패치 이후에만 사용 가능하다. 현재 코드 그대로는 강원/경북 제한과 동명이구 충돌이 남아 있다.

### Step 4. 로컬 산출물 검증

필수 체크:

- 기대 대상 수와 detail JSON 수 일치
- `city_id` 중복 0
- `(lDongRegnCd, lDongSignguCd)` 중복 0
- 동명이구 29개가 모두 존재
- `contenttypeid=39` 음식점 제외 유지
- 관광지/축제 총량이 기존 대비 비정상 급감하지 않음

### Step 5. S3 raw 신규 prefix 업로드

예:

```powershell
uv run python -m kr_details_pipeline.cli raw-ingest --input-dir data/KR/details_20260629 --output-dir data/KR/ingest/20260629 --bucket lovv-data-pipeline-dev-925273580929 --profile skn26_final --region us-east-1 --ingest-date 20260629 --overwrite
```

검증 기준:

- `upload_results.jsonl` uploaded 수가 detail JSON 수와 일치
- failed 0
- S3 key 중복 0
- 동명이구 29개가 모두 S3에 별도 key로 존재

### Step 6. 전처리 및 DynamoDB V2 재적재

전처리도 새 ingest date로 수행한다.

기준 prefix:

- `processed/KR/domain/20260629/`

DynamoDB는 기존 `TourKoreaDomainDataV2`에 바로 덮어쓰기 전에 dry-run/load candidate를 먼저 생성한다.

검증 기준:

- `city_metadata` 수가 기대 도시 수와 일치
- `visitor_statistics`는 도시 수 x 12개월과 일치
- 동명이구 PK가 `CITY#JUNG-GU`처럼 단독명으로 수렴하지 않음
- `CityDomainIndex`, `ProvinceDomainIndex`, `EntityTypeDomainIndex` 질의가 city_id/province 기준으로 정상 분리됨

## 6. 완료 판정 기준

재취득 완료는 다음 조건을 모두 만족해야 한다.

- 동명이구 29개가 raw/detail/S3/DynamoDB에서 모두 별도 도시로 존재
- `중구`, `동구`, `서구`, `남구`, `북구`, `강서구`, `고성군`이 단독 파일명 또는 단독 PK로 수렴하지 않음
- 관광지/축제 raw detail이 새 S3 prefix에 업로드됨
- 방문통계가 city_id 기준으로 월별 12건씩 분리됨
- V2 가이드와 취득 보고서의 수량이 새 기준으로 갱신됨

## 7. 권장 결론

지금 바로 재취득을 실행하는 것은 권장하지 않는다.

먼저 고유 key 패치를 적용하고 smoke 재취득으로 동명이구 4개를 검증한 뒤, 새 ingest date로 전국 전체를 다시 취득해야 한다. 기존 `20260625` raw와 V2 적재분은 참조용으로 보존하고, 신규 `20260629` 라인을 기준으로 S3 raw, processed domain, DynamoDB V2, vector index를 다시 맞추는 순서가 안전하다.
