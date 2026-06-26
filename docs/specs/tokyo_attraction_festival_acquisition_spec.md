# Spec: 도쿄 관광지·축제 데이터 취득

> 기준 계획서: `docs/japan_data_acquisition_plan.md` v0.4
> 기준 조사: `docs/reports/japan_data_source_license_investigation_report.md`, `docs/reports/japan_tourism_opendata_portal_directory.md`
> 문서 상태: 검토용 초안
> 작성일: 2026-06-17
> 담당 역할: Spec Agent

## 요약

이 문서는 Lovv 여행 추천 서비스에서 사용할 **도쿄도(JP-13)의 관광지(Attraction)·축제(Festival) 데이터**를 지자체 오픈데이터 중심으로 취득, 정규화, 검증, 저장하는 기준을 정의한다.

데이터 모델은 `City 1:N Attraction`, `City 1:N Festival` 관계를 기준으로 하며, 모든 Attraction·Festival은 기존 City 레코드의 `city_id`에 연결된다. 1차 소스는 디지털청 자치체표준 오픈데이터셋(`観光施設一覧`, `イベント一覧`)이며, 도쿄도 오픈데이터 카탈로그(CKAN)에서 취득한다.

## 전제

- 대상 국가는 일본, 첫 구현 대상은 도쿄도(JP-13)로 한정한다.
- 현재 단계는 PoC에서 Prod로의 이행이며, **비영리 기반으로 취득하되 상업 전환에 대비해 레코드마다 라이선스를 태깅**한다.
- 크롤러 런타임은 Python 3.12, HTTP는 `requests`를 기준으로 한다.
- City 데이터와 `city_id`는 기존 도시 취득 Spec(`docs/specs/city_data_acquisition_spec.md`)에서 관리되며, 본 Spec은 이를 의존한다.
- 지자체 오픈데이터 CSV는 **Shift-JIS(CP932) 인코딩**을 기본으로 가정한다(도쿄 관광시설 CSV 실측 확인).
- 본 Spec은 구현 요구사항을 준비하는 문서이며, 크롤러 구현 자체는 포함하지 않는다.

## 목표

- 도쿄도 오픈데이터 CKAN에서 자치체표준 `観光施設一覧`·`イベント一覧` 데이터셋을 발견·취득한다.
- 계획서에 정의된 Attraction·Festival 필드를 표준 스키마 매핑으로 취득한다.
- 목적지마다 정규화된 Attraction·Festival 레코드를 만들고, 각 레코드를 `city_id`에 연결한다.
- 모든 레코드에 출처, 라이선스, 취득 메타데이터, 필드별 수집 상태(`field_status`)를 기록한다.
- 안정적인 `attraction_id`·`festival_id`를 부여한다.
- 누락·불확실 값(특히 사진, 축제 개최일)을 후속 보정할 수 있도록 상태를 기록한다.
- 비영리 PoC와 상업 전환 양쪽에서 사용 가능하도록 소스를 라이선스로 격리한다.

## 비목표

- 도쿄도 외 도도부현, City 데이터 재수집은 이 Spec에서 다루지 않는다.
- 관광연맹·관광협회 등 **저작권(무단전재금지) 관광사이트의 스크래핑은 수행하지 않는다.**
- 사진의 자동 대량 수집은 수행하지 않는다(라이선스 리스크).
- 추천 점수, 랭킹, 일정 생성 로직은 정의하지 않는다.
- 외부 설명문 원문을 서비스 문구로 길게 복사해 저장하지 않는다.

## 사용자와 행위자

- Data Acquisition Agent: CKAN 발견, CSV 취득, 정규화 output 작성.
- 공식 확인 / Web Search Worker: 운영시간·입장료·축제 개최일 등 누락·최신성 보정.
- Human Reviewer: 모호한 값, city_id 매핑, 사진·저작권 민감 항목 검수.
- Downstream Recommendation Service: `city_id` 기준으로 Attraction·Festival을 소비.

## 데이터 모델과 관계

```text
City
 ├── Attraction   (City 1:N Attraction)
 └── Festival     (City 1:N Festival)
```

모든 Attraction·Festival은 반드시 하나의 `city_id`를 가진다. `city_id`는 도쿄도 시구정촌 코드(예: `131229` 葛飾区)를 기존 City 레코드에 매핑하여 부여한다.

## 출처 우선순위

### Attraction

| 우선순위 | 출처 | 주요 용도 | 라이선스 |
| --- | --- | --- | --- |
| 1 | 도쿄도 오픈데이터 CKAN `観光施設一覧`(자치체표준) | 명칭, 주소, 좌표, 운영시간, 요금, 설명, URL | CC-BY-4.0 (상업 가능) |
| 2 | Wikidata | 좌표·결손 보완, 다국어명 | CC0 (상업 무제약) |
| 3 | 공식 사이트(허가 기반, 표적) | 운영시간·입장료·사진 보정 | 사이트별 확인 |

### Festival

| 우선순위 | 출처 | 주요 용도 | 라이선스 |
| --- | --- | --- | --- |
| 1 | 도쿄도 오픈데이터 CKAN `イベント一覧`(자치체표준) | 축제·행사명, 장소, 개최기간, 설명, URL | CC-BY-4.0 (상업 가능) |
| 2 | Wikidata | 주요 축제 보완 | CC0 |
| 3 | 공식 사이트(허가 기반, 표적) | 연도별 개최일·사진 | 사이트별 확인 |

## 수집 방식

- 데이터셋 발견은 CKAN API `package_search`를 사용한다. 예: `https://catalog.data.metro.tokyo.lg.jp/api/3/action/package_search?q=観光施設&rows=200`, 축제는 `q=イベント`.
- 각 데이터셋의 `resources[]`에서 `format=CSV` 리소스의 `url`을 취득해 다운로드한다. 라이선스는 리소스 단위(`license_id`)로 판정한다.
- CSV는 **CP932로 디코딩**한다. UTF-8 가정은 금지한다.
- 컬럼은 자치체표준 스키마 기준으로 매핑하되, 구·시별 컬럼명 편차를 흡수할 수 있도록 별칭(alias) 매핑을 허용한다.
- 동일 시설·축제가 복수 소스에 있으면 명칭+좌표 근접도로 중복을 제거한다.

## 데이터 요구사항

### Attraction 필드 (← `観光施設一覧` 컬럼)

| 필드 | 필수 | 소스 컬럼 | 설명 |
| --- | --- | --- | --- |
| `attraction_id` | 필수 | 내부 생성 | 안정적 식별자. 예: `JP-13-131229-TORASAN-MUSEUM` |
| `city_id` | 필수 | `都道府県コード又は市区町村コード` 매핑 | 소속 도시(City) |
| `name` | 필수 | `名称` | 관광지명(일본어 원문) |
| `name_kana` | 권장 | `名称_カナ` | 가나 표기 |
| `name_en` | 권장 | `名称_英語` | 영어명 |
| `category` | 권장 | `POIコード` | 시설 분류 코드 |
| `address` | 필수 | `住所`(+`方書`) | 주소 |
| `latitude` / `longitude` | 필수 | `緯度` / `経度` | 좌표 |
| `opening_hours` | 권장 | `利用可能曜日`+`開始時間`+`終了時間` | 운영시간 |
| `opening_period` | 권장 | `利用可能日時特記事項` | 휴관일·계절 운영 등 |
| `admission_fee` | 권장 | `料金（基本）`+`料金（詳細）` | 입장료 |
| `description` | 필수 | `説明` | 설명(내부 한국어 요약 재작성) |
| `description_en` | 선택 | `説明_英語` | 영문 설명 |
| `access` | 선택 | `アクセス方法` | 교통 접근 |
| `parking` / `barrier_free` | 선택 | `駐車場情報` / `バリアフリー情報` | 부가 정보 |
| `phone` | 선택 | `連絡先電話番号` | 연락처 |
| `site_url` | 필수 | `URL` | 공식/안내 URL |
| `photo_url` | 권장 | `画像`(+`画像_ライセンス`) | 대표 사진. **표준 CSV에서 대개 빈 값 → `missing`/`needs_review`** |

### Festival 필드 (← `イベント一覧` 컬럼)

| 필드 | 필수 | 소스 컬럼 | 설명 |
| --- | --- | --- | --- |
| `festival_id` | 필수 | 내부 생성 | 안정적 식별자 |
| `city_id` | 필수 | 시구정촌 코드 매핑 | 개최 도시 |
| `name` | 필수 | `名称` | 축제·행사명 |
| `name_en` | 권장 | `名称_英語` | 영어명 |
| `address` | 필수 | `場所` / `住所` | 개최 장소 주소 |
| `latitude` / `longitude` | 권장 | `緯度` / `経度` | 좌표 |
| `period_text` | 필수 | `開始日時`·`終了日時` 원문 | 개최기간 원문 문자열 |
| `start_date` / `end_date` / `month` | 권장 | `開始日時` / `終了日時` 파싱 | 정규화 기간값 |
| `description` | 필수 | `説明` | 설명(내부 요약) |
| `organizer` | 선택 | `主催者` | 주최 |
| `site_url` | 필수 | `URL` | 공식/안내 URL |
| `photo_url` | 권장 | `画像` | 대표 사진(빈 값 가능) |

### 취득 메타데이터 (공통)

| 필드 | 설명 |
| --- | --- |
| `source_name`, `source_url`, `collected_at` | 출처와 취득 시각 |
| `license` | 예: `CC-BY-4.0`, `CC0` |
| `commercial_use_allowed` | true/false. 상업 전환 시 false 필터 기준 |
| `attribution_text` | 출처표기 문자열 |
| `field_status` | 필드별 `collected`/`needs_review`/`missing`/`blocked` |
| `data_confidence` | `high`/`medium`/`low` |
| `verified_at`, `verified_source_url`, `verification_note` | 공식 확인·검수 기록 |

## 요구사항 (기능)

- CKAN `package_search`로 도쿄도 `観光施設一覧`·`イベント一覧` 데이터셋을 발견하고 CSV 리소스 URL과 라이선스를 수집한다.
- CSV를 CP932로 디코딩해 자치체표준 컬럼을 위 필드로 매핑한다.
- 시구정촌 코드로 `city_id`를 연결하고, 연결 실패 레코드는 `needs_review`로 표시한다.
- 각 레코드에 출처·라이선스·취득 상태 메타데이터를 부여한다.
- 누락 좌표·결손 항목은 Wikidata(CC0)로 보완하고 출처를 구분 기록한다.
- 기존 출력에 병합하여 재실행 시 누적되도록 한다(City 파이프라인의 merge 방식 준용).

## Acceptance Criteria

- 도쿄도 최소 1개 이상의 구/시 `観光施設一覧`과 `イベント一覧`을 취득해 정규화 레코드를 생성한다.
- 모든 Attraction·Festival 레코드가 유효한 `city_id`를 가진다(미연결은 `needs_review`로 분리 보고).
- 모든 레코드가 `source_name`·`source_url`·`collected_at`·`license`·`commercial_use_allowed`를 가진다.
- 모든 정의 필드가 `collected`/`needs_review`/`missing`/`blocked` 중 하나의 상태를 가진다.
- CP932 CSV가 깨짐 없이 파싱되고, 葛飾区 샘플(3건)이 픽스처 테스트로 통과한다.
- `photo_url`이 비어 있는 경우 `missing`/`needs_review`로 표시되고 자동 핫링크 저장이 없다.

## 제약 (Constraints)

- 인코딩은 CP932 기준. UTF-8 단정 금지.
- 자치체표준이라도 구·시별 컬럼명·유무 편차가 있으므로 별칭 매핑과 결손 허용이 필요하다.
- 일부 구·시는 `観光施設`/`イベント` 데이터를 미게재할 수 있다 → 공백은 Wikidata 보완 또는 `missing`.
- 사진은 표준 CSV에서 대개 빈 값이며 라이선스가 불명확하므로 자동 수집·저장하지 않는다.
- 축제는 연도별 개최일이 바뀌므로 `period_text`와 정규화값을 함께 저장하고 최신성 검수 대상으로 둔다.
- 관광사이트(관광연맹/협회) 직접 스크래핑 금지(무단전재금지).
- 루트 `AGENTS.md` 보안·Workspace Boundary 규칙을 준수하며, 수집 산출물은 Git에 커밋하지 않는다(`data/` 제외 관행).

## 리스크와 가정

- (리스크) 자치체표준 준수도가 구·시마다 달라 컬럼 매핑이 일부 실패할 수 있다 → 별칭 매핑·결손 상태로 흡수.
- (리스크) `イベント一覧` 커버리지가 도쿄 내에서도 불균일하여 축제 데이터가 빈약할 수 있다 → Wikidata·공식(허가) 보강.
- (리스크) 시구정촌 코드와 City 레코드 불일치로 `city_id` 매핑 실패 가능 → `needs_review` 분리.
- (리스크) CKAN 호스트·데이터셋 구조 변경 → 발견 단계를 설정화하고 회귀 테스트로 감지.
- (가정) 도쿄 관광시설 CSV가 운영시간·요금·설명까지 포함한다(葛飾区 실측 확인). 사진만 결손.

## Task Breakdown

### Task: CKAN 취득 클라이언트 및 CP932 CSV 리더
- Purpose: 도쿄 CKAN에서 데이터셋을 발견하고 CSV를 안전하게 읽기 위함.
- Scope: `package_search` 호출, 리소스 URL·라이선스 추출, CP932 디코딩 리더. 정규화는 제외.
- Dependencies: 없음.
- Acceptance Criteria: 観光施設/イベント 데이터셋 목록과 CSV URL·license를 반환하고, 葛飾区 CSV를 깨짐 없이 파싱한다.
- Verification: 단위테스트(인코딩·리소스 파싱), 葛飾区 픽스처.

### Task: Attraction 정규화
- Purpose: `観光施設一覧` → Attraction 레코드 변환.
- Scope: 컬럼 매핑, attraction_id 생성, field_status 산출. 축제·city 매핑 제외.
- Dependencies: CKAN 클라이언트.
- Acceptance Criteria: 정의 필드가 매핑되고 상태가 부여된다. 사진 결손이 `missing`으로 표시된다.
- Verification: 매핑 단위테스트, 葛飾区 3건 스냅샷.

### Task: Festival 정규화
- Purpose: `イベント一覧` → Festival 레코드 변환.
- Scope: 컬럼 매핑, period 원문+정규화, festival_id 생성.
- Dependencies: CKAN 클라이언트.
- Acceptance Criteria: 개최기간이 원문·정규화 모두 저장되고 city_id 자리표시자가 채워진다.
- Verification: 기간 파싱 단위테스트.

### Task: city_id 매핑 및 병합
- Purpose: Attraction·Festival을 City에 연결하고 재실행 누적.
- Scope: 시구정촌 코드→city_id 매핑, 병합·중복제거.
- Dependencies: Attraction·Festival 정규화, 기존 City 레코드.
- Acceptance Criteria: 모든 레코드가 city_id 보유 또는 `needs_review` 분리. 재실행 시 덮어쓰지 않고 누적.
- Verification: 매핑·병합 단위테스트.

### Task: 라이선스·출처 태깅
- Purpose: 비영리/상업 전환 게이트를 위한 메타데이터 부여.
- Scope: source/license/commercial_use_allowed/attribution_text 기록, 게이트 함수.
- Dependencies: 정규화 결과.
- Acceptance Criteria: 전 레코드가 라이선스 메타데이터를 가지고, `commercial_use_allowed=false` 필터가 동작한다.
- Verification: 태깅·필터 단위테스트.

### Task(선택): Wikidata 보완
- Purpose: 좌표·결손·미게재 구/시 보완.
- Scope: Wikidata SPARQL 조회(CC0), 좌표·다국어명 보강.
- Dependencies: 정규화 결과.
- Acceptance Criteria: 결손 좌표가 보완되고 출처가 Wikidata로 구분 기록된다.
- Verification: 보완 전후 채움율 비교.

## Verification

- 단위테스트: CP932 디코딩, 리소스 파싱, 컬럼 매핑, 기간 파싱, city_id 매핑, 라이선스 게이트.
- 회귀 픽스처: `葛飾区(131229) 観光施設一覧` 3건을 고정 입력으로 사용.
- 통합 확인: 도쿄 23구 중 표본 수집 후 필드 채움율(특히 `city_name`/좌표/운영시간/요금/사진)과 `city_id` 연결율을 집계해 보고한다.
- 라이선스 점검: 전 레코드의 `license`·`commercial_use_allowed` 존재와, 상업 빌드에서 `false` 제외가 동작하는지 확인한다.
