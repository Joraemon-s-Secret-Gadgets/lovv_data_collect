# KR Wikipedia 전국 취득 라인 검토 보고서

- 작성일: 2026-06-29
- 검토 범위: `crawling/KR/city_wikipedia_acquisition.py`, `crawling/KR/pipeline.py`, `crawling/KR/normalizer.py`, `crawling/KR/provinces.py`, `crawling/KR/targets/*.json`, `data/KR/cities.json`, `data/KR/prefectures.json`
- 결론: 전국 범위 확장은 현재 산출물 기준으로 완료되어 있다. 다만 Wikipedia 취득 품질은 일부 target title과 field_status 산정에서 보정이 필요하다.

## 1. 판단 요약

전국 수집 범위 자체는 확장되어 있다.

- province target 파일: 17개
- target 합계: 229개
- `MUNICIPALITY_EN_MAP`: 229개
- `validate_target_coverage()`: 누락 0개
- 현재 `data/KR/cities.json`: 229개
- 현재 `data/KR/prefectures.json`: 17개
- `city_id` 중복: 0개
- `city_name_en` 중복: 0개
- target 기준 기대 `city_id` 누락: 0개

따라서 "전국 17개 시도 단위로 Wikipedia 취득을 돌릴 수 있는가"와 "현재 산출물이 전국 target 수량과 맞는가"는 Yes다.

하지만 "Wikipedia에서 모든 도시 정보를 올바른 문서에서 안정적으로 취득했는가"는 No다. 아래 품질 문제가 남아 있다.

## 2. 주요 Findings

### P1. `광주시`, `영광군`이 동음이의어 페이지에서 취득되었다

현재 target이 단독명으로 되어 있어 Wikipedia 동음이의어 페이지를 source로 사용했다.

| city_id | source_url | 현재 description |
|---|---|---|
| `KR-41-GWANGJU-GYEONGGI` | `https://ko.wikipedia.org/wiki/광주시` | `광주시의 다른 뜻은 다음과 같다.` |
| `KR-46-YEONGGWANG` | `https://ko.wikipedia.org/wiki/영광군` | `영광군은 다음 등을 가리킨다.` |

대상 파일:

- `crawling/KR/targets/gyeonggi_municipalities_ko.json`
- `crawling/KR/targets/jeonnam_municipalities_ko.json`

권장 조치:

- target title을 실제 행정구역 문서 제목으로 disambiguate한다.
- 예: `광주시 (경기도)`, `영광군 (전라남도)` 형태를 확인 후 적용한다.
- `MUNICIPALITY_EN_MAP` key도 target title과 일치하도록 조정한다.
- 해당 2개 도시는 재취득한다.

### P1. 좌표 누락 도시 9개가 남아 있다

현재 `latitude` 또는 `longitude`가 없는 도시는 9개다.

| city_id | city_name_ko | city_name_en |
|---|---|---|
| `KR-11-JUNG-SEOUL` | 중구 (서울특별시) | `JUNG-SEOUL` |
| `KR-26-DONG-BUSAN` | 동구 (부산광역시) | `DONG-BUSAN` |
| `KR-26-GANGSEO-BUSAN` | 강서구 (부산광역시) | `GANGSEO-BUSAN` |
| `KR-26-JUNG-BUSAN` | 중구 (부산광역시) | `JUNG-BUSAN` |
| `KR-26-SEO-BUSAN` | 서구 (부산광역시) | `SEO-BUSAN` |
| `KR-27-DONG-DAEGU` | 동구 (대구광역시) | `DONG-DAEGU` |
| `KR-27-NAM-DAEGU` | 남구 (대구광역시) | `NAM-DAEGU` |
| `KR-28-DONG-INCHEON` | 동구 (인천광역시) | `DONG-INCHEON` |
| `KR-29-DONG-GWANGJU` | 동구 (광주광역시) | `DONG-GWANGJU` |

권장 조치:

- Wikipedia coordinate extraction 실패 시 사용할 행정구역별 좌표 fallback map을 둔다.
- 또는 Nominatim query를 `대한민국 {광역시도} {구군명}청` 형태로 보강한다.
- 보정 후 9개 도시만 부분 재취득 또는 보정 스크립트로 갱신한다.

### P2. 빈 `site_urls`가 `collected`로 표시된다

현재 `site_urls`가 빈 리스트인데 `field_status.site_urls = collected`인 도시가 5개다.

| city_id | city_name_ko |
|---|---|
| `KR-27-DALSEONG` | 달성군 |
| `KR-31-JUNG-ULSAN` | 중구 (울산광역시) |
| `KR-41-GWANGJU-GYEONGGI` | 광주시 |
| `KR-46-SUNCHEON` | 순천시 |
| `KR-46-YEONGGWANG` | 영광군 |

원인:

- `normalizer._status()`가 빈 리스트를 missing으로 보지 않는다.

권장 조치:

- `_status()`가 `[]`, `{}` 같은 빈 container를 `STATUS_MISSING`으로 처리하도록 수정한다.
- 테스트에서 빈 `site_urls` 상태를 검증한다.

### P2. 전국 실행 경로 테스트가 부족하다

현재 `crawling/KR/tests/test_city_wikipedia_acquisition.py`는 통과하지만, `--province-id`, `--all-provinces`, `acquire_province()`, `acquire_all_provinces()`를 직접 검증하는 테스트가 부족하다.

실행 결과:

```text
uv run python -m pytest crawling/KR/tests/test_city_wikipedia_acquisition.py -q --basetemp .cache/pytest-tmp -p no:cacheprovider
14 passed
```

권장 조치:

- `--province-id KR-11` target resolution 테스트
- `--all-provinces`가 17개 province를 순회하는지 테스트
- 기존 `cities.json`이 있을 때 skip count가 맞는지 테스트
- province별 target 수 합산과 `ProvinceResult` accounting 테스트

### P3. 기존 2026-06-26 보고서의 경북 수량이 현재 산출물과 다르다

`docs/reports/kr_nationwide_wikipedia_acquisition_20260626.md`에는 경북이 23개로 적혀 있으나, 현재 target과 data는 22개다.

- `crawling/KR/targets/gyeongbuk_municipalities_ko.json`: 22개
- `data/KR/cities.json`의 `KR-47`: 22개

권장 조치:

- 기존 보고서의 경북 수량을 현재 산출물 기준으로 정정하거나, 보고서가 당시 snapshot이라는 점을 명시한다.

## 3. 정상 동작으로 확인된 부분

### 3.1 CLI와 pipeline은 전국 실행 옵션을 갖고 있다

- `city_wikipedia_acquisition.py`
  - `--province-id`
  - `--all-provinces`
  - `--collect-visitor-stats`
  - `--merge`
  - `--upload-to-s3`

- `pipeline.py`
  - `acquire_province()`
  - `acquire_all_provinces()`
  - `_PROVINCE_TARGET_MAP` 17개 province

### 3.2 현재 target/data 수량은 일치한다

| 항목 | 수량 |
|---|---:|
| target files | 17 |
| target total | 229 |
| `MUNICIPALITY_EN_MAP` | 229 |
| `cities.json` | 229 |
| `prefectures.json` | 17 |
| target coverage gap | 0 |
| expected city_id missing | 0 |
| city_id duplicates | 0 |
| city_name_en duplicates | 0 |

### 3.3 기본 identity 필드는 모두 채워져 있다

현재 `cities.json` 기준:

- missing `city_name_en`: 0
- missing `prefecture_id`: 0
- missing `description`: 0
- missing `source_url`: 0
- bad identity (`KR-UNKNOWN`, blank city_name_en, blank prefecture_id): 0

## 4. 품질 지표

| 지표 | 수량 | 해석 |
|---|---:|---|
| `description=needs_review` | 229 | 현재 정책상 Wikipedia description은 전부 검수 대상으로 표시된다. |
| `climate_table=collected` | 73 | 자동 취득된 기후표 |
| `climate_table=needs_review` | 156 | Wikipedia에서 기후표 자동 취득 실패, 수동 확인 필요 |
| missing coordinates | 9 | 보정 필요 |
| empty `site_urls` | 5 | 일부는 정상일 수 있으나 status 산정은 수정 필요 |
| potential disambiguation page | 2 | 반드시 target 보정 필요 |

## 5. 검증 명령

```powershell
uv run python -m pytest crawling/KR/tests/test_city_wikipedia_acquisition.py -q --basetemp .cache/pytest-tmp -p no:cacheprovider
uv run python -m compileall -q crawling/KR/city_wikipedia_acquisition.py crawling/KR/pipeline.py crawling/KR/normalizer.py crawling/KR/provinces.py
uv run python -c "from pathlib import Path; from crawling.KR.provinces import validate_target_coverage; print(len(validate_target_coverage(Path('crawling/KR/targets'))))"
```

결과:

- pytest: 14 passed
- compileall: 성공
- target coverage missing: 0

## 6. 결론

전국 확장 자체는 현재 코드와 산출물 기준으로 동작한다. `cities.json`과 `prefectures.json`도 전국 target 수량과 맞는다.

다만 Wikipedia 취득 품질은 아직 "완료"로 보기 어렵다. 최소한 다음 3개는 재취득 전에 보정해야 한다.

1. `광주시`, `영광군` target title disambiguation 보정
2. 좌표 누락 9개 도시 fallback 보정
3. 빈 `site_urls`를 `collected`로 표시하는 field_status 산정 수정

그 다음 `--province-id`/`--all-provinces` 테스트를 추가하고, 보정된 도시를 부분 재취득하는 순서가 안전하다.
