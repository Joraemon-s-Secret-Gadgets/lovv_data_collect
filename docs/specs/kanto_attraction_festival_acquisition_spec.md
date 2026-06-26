# Spec: 관동지방 관광지·축제 데이터 취득

> 기준 계획서: `docs/japan_data_acquisition_plan.md` v0.4
> 기준 조사: `docs/reports/japan_data_source_license_investigation_report.md`, `docs/reports/japan_tourism_opendata_portal_directory.md`
> 선행 Spec: `docs/specs/tokyo_attraction_festival_acquisition_spec.md` (도쿄 단일 현 기준)
> 문서 상태: 검토용 초안
> 작성일: 2026-06-22
> 담당 역할: Spec Agent

## Summary

Lovv 여행 추천 서비스에서 사용할 **관동지방(Kanto) 7개 도도부현의 관광지(Attraction)·축제(Festival) 데이터**를 지자체 오픈데이터 중심으로 취득·정규화·검증·저장하는 기준을 정의한다.

관동지방 대상 현은 `crawling/JP/prefectures.py` 기준 다음 7개다.

| prefecture_id | 현(한국어) | 현(일본어) | 영문 |
| --- | --- | --- | --- |
| JP-08 | 이바라키현 | 茨城県 | Ibaraki |
| JP-09 | 도치기현 | 栃木県 | Tochigi |
| JP-10 | 군마현 | 群馬県 | Gunma |
| JP-11 | 사이타마현 | 埼玉県 | Saitama |
| JP-12 | 지바현 | 千葉県 | Chiba |
| JP-13 | 도쿄도 | 東京都 | Tokyo |
| JP-14 | 가나가와현 | 神奈川県 | Kanagawa |

데이터 모델은 `City 1:N Attraction`, `City 1:N Festival` 관계를 따르며, 모든 Attraction·Festival은 기존 City 레코드의 `city_id`에 연결된다. **본 Spec은 도쿄(JP-13)를 1차 레퍼런스 구현으로 완성한 뒤, 동일한 정규화 스키마를 유지한 채 소스 어댑터를 추가해 관동 6현으로 확장하는 2단계 전략**을 채택한다.

### 선행 Spec과의 관계

`tokyo_attraction_festival_acquisition_spec.md`는 도쿄도 단일 CKAN(`catalog.data.metro.tokyo.lg.jp`) 기준의 Attraction·Festival 취득을 정의하지만, **현재 해당 구현 코드는 존재하지 않는다**(`crawling/JP`에는 Wikipedia City 취득 코드만 있음). 본 Spec은 그 도쿄 Spec을 Phase 1의 상세 기준으로 그대로 인용·승계하고, Phase 2에서 다중 플랫폼·다중 현 확장 요구사항만 추가로 규정한다. 도쿄 Spec과 본 Spec이 충돌하면 도쿄 범위에 한해 도쿄 Spec을 Source of Truth로 둔다.

## Goals

- 도쿄도 오픈데이터(CKAN)에서 자치체표준 `観光施設一覧`·`イベント一覧` 데이터셋을 취득하는 **레퍼런스 파이프라인을 구현**한다(현재 미구현).
- 동일 정규화 스키마를 유지한 채, 플랫폼별 소스 어댑터(CKAN / BODIK / dataeye / 독자CMS)를 통해 **관동 6현으로 확장**한다.
- 계획서에 정의된 Attraction·Festival 필드를 표준 스키마 매핑으로 취득한다.
- 모든 레코드를 기존 City 레코드의 `city_id`에 연결한다.
- 모든 레코드에 출처·라이선스·취득 메타데이터·필드별 수집 상태(`field_status`)를 기록한다.
- 비영리 PoC와 상업 전환 양쪽에서 사용 가능하도록 소스를 라이선스 단위로 격리·태깅한다.
- POI 공백 현(군마·가나가와 등)은 Wikidata(CC0)·OSM 보완 대상으로 분리 관리한다.

## Non-Goals

- City 데이터 재수집은 다루지 않는다. City와 `city_id`는 기존 City 취득 Spec(`docs/specs/city_data_acquisition_spec.md`)에서 관리된다. 단, 관동 6현 City 미수집분의 선행 필요성은 "리스크와 의존성"에 명시한다.
- 관광연맹·관광협회 등 **저작권(무단전재금지) 관광사이트의 스크래핑은 수행하지 않는다.**
- 사진의 자동 대량 수집은 수행하지 않는다(라이선스 리스크).
- 추천 점수·랭킹·일정 생성 로직은 정의하지 않는다.
- 외부 설명문 원문을 서비스 문구로 길게 복사 저장하지 않는다(내부 요약 재작성).
- 관동 외 도도부현(주부·간사이 등)은 본 Spec 범위가 아니다.

## User Flow

```text
[Phase 1] 도쿄 CKAN 레퍼런스
package_search(観光施設/イベント) → CSV(CP932) 취득 → 자치체표준 컬럼 매핑
→ Attraction/Festival 정규화 → city_id 매핑 → 라이선스 태깅 → data/JP merge

[Phase 2] 관동 6현 확장
현별 소스 어댑터 선택(CKAN/BODIK/dataeye/독자CMS) → 동일 정규화 스키마로 변환
→ city_id 매핑 → 라이선스 태깅 → POI 공백 현은 Wikidata/OSM 보완 → merge
```

## 관동 현별 소스 매핑 (조사 기준)

> 출처: `japan_tourism_opendata_portal_directory.md` §3.2. URL·플랫폼 신뢰도 높음(2026-06 직접 확인). 관광 POI 보유도·건수는 추정(신뢰도: 중간) — **수집 직전 각 포털에서 `観光施設`/`イベント` 데이터셋 유무 재확인 필수**.

| 현 | 포털 | 플랫폼 | 관광 POI | 라이선스(상업) | 취득 난이도 |
| --- | --- | --- | --- | --- | --- |
| 東京 JP-13 | catalog.data.metro.tokyo.lg.jp | CKAN | ○ 観光施設(구별) | CC-BY 4.0 | 낮음(레퍼런스) |
| 千葉 JP-12 | opendata.pref.chiba.lg.jp | dataeye | ○ 관광시설·이벤트 | 자유(상업가) | 중간 |
| 埼玉 JP-11 | opendata.pref.saitama.lg.jp | dataeye | ○ 運輸·観光 155건 | 자유(상업가) | 중간 |
| 栃木 JP-09 | odcs.bodik.jp/090000/ | BODIK CKAN | △ GIS 분산 | CC-BY | 중간 |
| 茨城 JP-08 | ibaraki-opendata.jp | 독자CMS/CSV | △ 빈약 | CC-BY 4.0 | 높음 |
| 神奈川 JP-14 | catalog.opendata.pref.kanagawa.jp | CKAN | ✕ 현 카탈로그 빈약 | 상업가 | 높음(POI 공백) |
| 群馬 JP-10 | toukei.pref.gunma.jp | 통계포털/비CKAN | ✕ 사실상 부재 | 개별 | 매우 높음(POI 부재) |

핵심 시사점:

- **플랫폼이 4종(CKAN·BODIK·dataeye·독자CMS)으로 갈린다.** CKAN과 BODIK은 동일 `package_search` API 계열이라 어댑터 공유가 가능하다. dataeye는 별도 WebAPI/CSV, 이바라키는 독자 CMS라 별도 어댑터가 필요하다.
- **군마는 관광 POI가 사실상 부재**하므로 오픈데이터 취득 대상에서 제외하고 Wikidata/OSM 보완 대상으로만 둔다.
- **가나가와는 현 카탈로그가 빈약**하므로 시정촌 단위 카탈로그 확인 또는 Wikidata 보완으로 처리한다.

## Requirements (기능)

### 공통

- 정규화 출력 스키마는 도쿄 Spec의 Attraction·Festival 필드와 취득 메타데이터를 그대로 따른다(필드 정의는 도쿄 Spec §"데이터 요구사항" 인용).
- 모든 레코드는 `source_name`, `source_url`, `collected_at`, `license`, `commercial_use_allowed`, `attribution_text`, `field_status`, `data_confidence`를 가진다.
- 시구정촌 코드 → `city_id` 매핑으로 City와 연결하고, 실패 레코드는 `needs_review`로 분리 보고한다.
- 기존 출력(`data/JP`)에 병합하여 재실행 시 누적(덮어쓰기 금지)한다.
- 누락 좌표·결손은 Wikidata(CC0)로 보완하고 출처를 구분 기록한다.

### Phase 1 — 도쿄 CKAN 레퍼런스 (선행 Spec 승계)

- CKAN `package_search`로 도쿄 `観光施設一覧`·`イベント一覧` 데이터셋을 발견하고 CSV URL·라이선스를 수집한다.
- CSV는 **CP932로 디코딩**한다(UTF-8 단정 금지).
- 자치체표준 컬럼을 Attraction·Festival 필드로 매핑(구·시별 컬럼명 편차는 별칭 매핑으로 흡수).
- 葛飾区(131229) 픽스처로 회귀 검증.

### Phase 2 — 관동 6현 확장

- 소스 어댑터 인터페이스를 정의한다: `discover() -> [데이터셋]`, `fetch_csv(resource) -> rows`, `license_of(resource)`.
- 어댑터 구현체:
  - `CkanAdapter`: 도쿄·가나가와·栃木(BODIK) 공용(`package_search` 계열).
  - `DataeyeAdapter`: 지바·사이타마.
  - `IbarakiCmsAdapter`: 이바라키 독자 CMS.
- 현별 인코딩·컬럼 편차를 어댑터가 흡수하고, 정규화 스키마는 공통으로 유지한다.
- 군마(POI 부재)는 오픈데이터 취득 스킵, Wikidata/OSM 보완 큐로만 등록한다.
- 현별 취득 결과의 필드 채움율과 `city_id` 연결율을 집계해 보고한다.

## Acceptance Criteria

- (Phase 1) 도쿄 최소 1개 구/시의 `観光施設一覧`·`イベント一覧`을 취득해 정규화 레코드를 생성하고, 葛飾区 3건 픽스처 테스트가 통과한다.
- (Phase 2) 관동 6현 중 **dataeye 2현(지바·사이타마)과 BODIK 1현(栃木) 이상**에서 최소 1개 데이터셋을 정규화 레코드로 생성한다.
- 모든 Attraction·Festival 레코드가 유효한 `city_id`를 가진다(미연결은 `needs_review`로 분리 보고).
- 모든 레코드가 `source_name`·`source_url`·`collected_at`·`license`·`commercial_use_allowed`를 가진다.
- 모든 정의 필드가 `collected`/`needs_review`/`missing`/`blocked` 중 하나의 상태를 가진다.
- `commercial_use_allowed=false` 필터가 상업 빌드에서 동작한다.
- 군마는 오픈데이터 미취득이 의도된 결정임을 보고서에 명시하고 Wikidata/OSM 보완 큐에 등록한다.
- `photo_url`이 비어 있으면 `missing`/`needs_review`로 표시되고 자동 핫링크 저장이 없다.

## Constraints

- 인코딩은 CP932 기준(도쿄). 현별로 UTF-8/CP932가 섞일 수 있으므로 어댑터에서 인코딩을 감지·설정화한다.
- 자치체표준이라도 현·시별 컬럼명·유무 편차가 크므로 별칭 매핑과 결손 허용이 필요하다.
- 관광사이트(관광연맹/협회) 직접 스크래핑 금지(무단전재금지).
- 라이선스가 "개별 확인" 또는 NC(비영리)인 소스는 `commercial_use_allowed=false`로 격리한다(예: 국토수치정보 P12).
- 루트 `AGENTS.md` 보안·Workspace Boundary 규칙 준수. 수집 산출물은 Git에 커밋하지 않는다(`data/` 제외 관행).
- 크롤러 런타임 Python 3.12, HTTP는 `requests` 기준.

## Risks (리스크와 가정)

- (의존성) **관동 6현 City 데이터가 아직 미수집**이다. 현재 `data/JP/cities.json`은 도쿄 62건뿐이고, `pipeline.py`에 도쿄 전용 하드락(`TOKYO_PREFECTURE_ID`)이 있다. Attraction·Festival의 `city_id` 매핑을 위해 6현 City 선행 취득(하드락 일반화 포함)이 필요하다 → 별도 City 확장 작업과 순서 조율 필요. (신뢰도: 높음 — 코드·데이터 직접 확인)
- (리스크) 현별 플랫폼이 4종으로 갈려 단일 어댑터로 커버 불가 → 어댑터 추상화로 흡수하되 이바라키 독자 CMS는 개별 구현 비용이 크다.
- (리스크) 군마는 관광 POI 부재, 가나가와는 카탈로그 빈약 → 오픈데이터만으로는 커버리지 공백 → Wikidata/OSM 보완 필수.
- (리스크) `イベント一覧` 커버리지가 현 내에서도 불균일 → 축제 데이터가 빈약할 수 있음 → Wikidata·공식(허가) 보강.
- (리스크) 포털 호스트·데이터셋 구조 변경 → 발견 단계를 설정화하고 회귀 테스트로 감지.
- (가정) dataeye(지바·사이타마), BODIK(栃木)은 자치체표준 観光施設 데이터셋을 제공한다(조사 기준, 신뢰도: 중간 — 수집 직전 재확인 대상).

## Task Breakdown

### Task: Phase 1 — 도쿄 CKAN 레퍼런스 파이프라인 구현
- Purpose: 미구현 상태인 도쿄 Attraction/Festival CKAN 취득을 완성해 이후 확장의 레퍼런스로 삼기 위함.
- Scope: 도쿄 Spec의 CKAN 클라이언트·CP932 리더·Attraction/Festival 정규화·city_id 매핑·라이선스 태깅 구현. Phase 2 어댑터·6현은 제외.
- Dependencies: 기존 도쿄 City 레코드(있음).
- Acceptance Criteria: 도쿄 Spec의 Acceptance Criteria 전부 충족, 葛飾区 픽스처 통과.
- Verification: 단위테스트(CP932·리소스 파싱·컬럼 매핑·기간 파싱·라이선스 게이트), 葛飾区 3건 스냅샷.

### Task: 소스 어댑터 추상화 정의
- Purpose: 플랫폼 4종을 공통 인터페이스로 흡수해 정규화 스키마를 단일화하기 위함.
- Scope: `SourceAdapter` 인터페이스(`discover`/`fetch_csv`/`license_of`)와 CKAN 어댑터(도쿄·가나가와·栃木 공용) 정의. dataeye/이바라키 어댑터는 후속 Task.
- Dependencies: Phase 1.
- Acceptance Criteria: 도쿄 파이프라인이 `CkanAdapter`를 통해 동작(리팩터링 회귀 없음).
- Verification: 도쿄 기존 테스트 그대로 통과 + 어댑터 단위테스트.

### Task: dataeye 어댑터 (지바·사이타마)
- Purpose: 관동 내 POI가 비교적 풍부한 2현을 확장 1순위로 취득.
- Scope: dataeye WebAPI/CSV 발견·취득·라이선스 판정. 정규화는 공통 모듈 재사용.
- Dependencies: 소스 어댑터 추상화.
- Acceptance Criteria: 지바·사이타마 각 1개 데이터셋 이상 정규화 레코드 생성, city_id 연결율 보고.
- Verification: 현별 픽스처 단위테스트, 채움율 집계.

### Task: BODIK 어댑터 검증 (栃木)
- Purpose: BODIK CKAN 계열을 CkanAdapter로 커버 가능한지 확인하고 栃木 취득.
- Scope: `odcs.bodik.jp/090000/` package_search 조직 필터 취득. GIS 분산 데이터 매핑.
- Dependencies: 소스 어댑터 추상화.
- Acceptance Criteria: 栃木 1개 데이터셋 이상 정규화, CkanAdapter 재사용 확인.
- Verification: 栃木 픽스처 단위테스트.

### Task: 이바라키 독자 CMS 어댑터 (선택/후순위)
- Purpose: 비CKAN 독자 CMS 소스 취득.
- Scope: ibaraki-opendata.jp CSV 목록 파싱·취득. POI 빈약 → 최소 취득.
- Dependencies: 소스 어댑터 추상화.
- Acceptance Criteria: 최소 1개 観光 데이터셋 취득 또는 "미게재" 결론을 보고.
- Verification: 픽스처 단위테스트 또는 미게재 근거 기록.

### Task: POI 공백 현 보완 정책 (군마·가나가와)
- Purpose: 오픈데이터로 커버 불가한 현의 처리 방침 확정.
- Scope: 군마(POI 부재)·가나가와(카탈로그 빈약)를 Wikidata(CC0)/OSM 보완 큐로 등록. 실제 Wikidata 보완은 선택 Task.
- Dependencies: 어댑터 Task들.
- Acceptance Criteria: 두 현이 보완 큐에 등록되고, 의도된 오픈데이터 스킵이 보고서에 기록.
- Verification: 보완 큐 산출물·보고서 확인.

### Task: 라이선스·출처 태깅 및 상업 전환 게이트
- Purpose: 비영리/상업 전환 게이트를 위한 메타데이터 부여.
- Scope: source/license/commercial_use_allowed/attribution_text 기록, `false` 필터 함수. 현별 라이선스 편차(개별/NC) 반영.
- Dependencies: 정규화 결과.
- Acceptance Criteria: 전 레코드가 라이선스 메타데이터 보유, `commercial_use_allowed=false` 필터 동작.
- Verification: 태깅·필터 단위테스트.

## Verification

- 단위테스트: CP932/인코딩 감지, CKAN·BODIK·dataeye 리소스 파싱, 컬럼 매핑, 기간 파싱, city_id 매핑, 라이선스 게이트.
- 회귀 픽스처: `葛飾区(131229) 観光施設一覧` 3건 고정 입력 + 지바·사이타마·栃木 각 현 픽스처.
- 통합 확인: 관동 표본 수집 후 현별 필드 채움율(좌표/운영시간/요금/사진)과 `city_id` 연결율을 집계해 보고.
- 라이선스 점검: 전 레코드의 `license`·`commercial_use_allowed` 존재와 상업 빌드 `false` 제외 동작 확인.
- 커버리지 보고: 군마·가나가와 오픈데이터 공백과 Wikidata/OSM 보완 큐 등록 상태 명시.

## 진행 전 사용자 확인 필요

- 본 Spec은 **Attraction/Festival 도쿄 우선 + 관동 6현 확장**을 다룬다. 그러나 6현 City가 미수집이라 `city_id` 매핑이 막힌다. City 6현 확장(파이프라인 하드락 일반화)을 본 작업 **이전에 별도 트랙으로 선행**할지, 아니면 Phase 1(도쿄)만 먼저 완료하고 City 확장과 병행할지 결정이 필요하다.
- Spec 승인 후 `Task Agent` 단계에서 위 Task를 Subtask로 분해한다(`AGENTS.md` 흐름).
