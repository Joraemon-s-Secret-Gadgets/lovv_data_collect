# 일본 관광 오픈데이터 포털 디렉터리

> 문서 버전: v1.0
> 작성일: 2026-06-17
> 대상: Lovv 일본(JP) 관광지 데이터 취득
> 관련 문서: [japan_data_source_license_investigation_report.md](./japan_data_source_license_investigation_report.md)
> 성격: 관광 데이터를 합법적으로 취득 가능한 오픈데이터 포털 목록. 법률 자문 아님 — 데이터셋 단위 라이선스는 개별 확인 필요.

---

## 0. 사용 안내

본 디렉터리는 일본 관광지(Attraction) 데이터를 **오픈데이터(라이선스 명확)** 경로로 취득하기 위한 포털을 계층별로 정리한 것이다. 지자체 관광사이트(観光連盟/観光協会 운영)는 대부분 무단전재금지·상업불가이므로 본 목록에서 제외하며, 데이터 취득은 아래 포털 경로를 사용한다.

표기 약속: 관광 POI 보유도는 ◎(풍부)/○(있음)/△(통계·부분)/✕(POI 없음·통계만). 라이선스의 "상업"은 출처표기 전제 상업 이용 가부.

## 1. 국가·전국 집약 계층 (최우선 진입점)

| 포털 | URL | 제공 | 라이선스(상업) | 비고 |
| --- | --- | --- | --- | --- |
| e-Govデータポータル(구 DATA.GO.JP) | https://www.data.go.jp/ | 국가+지자체 오픈데이터 횡단 전문검색, 메타데이터 API | 데이터셋별(대부분 CC-BY, 상업가) | 47현 안 돌고 観光施設 횡단검색하는 1차 진입점 |
| 国土数値情報 | https://nlftp.mlit.go.jp/ksj/ | 관광자원 P12, 행정구역, 좌표 등 GIS | P12=非商用(비영리만), 기타 다수 PDL1.0(상업가) | P12는 전국 관광지 베이스(비영리). 상업 시 제외 |
| e-Stat(정부통계포털) | https://www.e-stat.go.jp/ | 관광청 숙박여행통계조사 등 관광 통계 | 政府標準2.0=CC-BY 4.0(상업가) | 방문객·숙박 통계. 디지털관광통계의 상업 대체 |
| 自治体標準オープンデータセット(디지털청) | https://www.digital.go.jp/policies/open_data | 観光施設一覧 표준 스키마 정의 | 표준(데이터는 각 지자체) | 47현 데이터 정규화 매핑 기준 |
| デジタル観光統計(일본관광진흥협회) | https://www.nihon-kankou.or.jp/home/jigyou/research/d-toukei/ | 도도부현/시구정촌 방문객 수(월별) | CC-BY 4.0이나 영리 시 사전 서면동의 필요 | 정부 아님(공익사단법인). 비영리는 사용가 |
| 全国観光情報データベース(일본관광진흥협회) | (Google 비즈니스 프로필 연동) | 관광지점 10만 곳 | 공개 API 아님 | 직접 취득 불가. 참고용 |

## 2. 플랫폼 백엔드 계층 (여러 현을 한 API로)

47현 포털의 다수가 두 공통 플랫폼 위에 있어, 커넥터 2개로 광범위하게 커버된다.

### 2.1 BODIK ODCS (CKAN 단일 백엔드)
- API/카탈로그: https://data.bodik.jp/ (`/api/3/action/package_search?q=観光&fq=organization:<코드>`)
- 라이선스: 기관 공통 CC-BY 4.0(상업가), 접근: CKAN API + CSV
- 소속 현(조직코드): 栃木(090000), 長野(nagano/200000), 三重(240001), 滋賀(shiga-pref), 京都(260002), 大阪(270008), 和歌山(300004), 山口(yamaguchi), 福岡(400009), 佐賀(410004/saga), 長崎(420000), 熊本(430005), 大分(440001), 宮崎(450006), 鹿児島(460001/kagoshima), 沖縄(470007) — 16현+

### 2.2 dataeye (一般社団法人 데이터클레이들)
- 플랫폼: 각 현별 서브도메인(예: `*.dataeye.jp`), WebAPI + CSV
- 라이선스: 데이터셋별(자유 이용/CC-BY/PDL 혼재, 대체로 상업가)
- 소속 현: 岩手, 宮城, 千葉, 埼玉, 島根, 岡山, 広島 — 7현

## 3. 도도부현 포털 (47)

플랫폼 표기: BODIK=BODIK CKAN, dataeye=dataeye, CKAN=독자 CKAN, Shirasagi/독자/정적=비CKAN. 관광 POI 보유도는 앞선 조사 기준(신뢰도: URL·플랫폼=높음, POI 건수=중간).

### 3.1 홋카이도·도호쿠

| 현 | 포털 URL | 플랫폼 | 관광 POI | 라이선스(상업) |
| --- | --- | --- | --- | --- |
| 北海道 | https://www.harp.lg.jp/opendata/ | Shirasagi/CSV | △ 시정촌 POI | CC-BY |
| 青森 | https://opendata.pref.aomori.lg.jp/ | Shirasagi/WebAPI+CSV | △ 통계 중심 | CC-BY |
| 岩手 | https://iwate.dataeye.jp/ | dataeye | △ 빈약 | 자유(상업가) |
| 宮城 | https://miyagi.dataeye.jp/ | dataeye | △ 観光名所 태그 | PDL/CC-BY |
| 秋田 | https://ckan.pref.akita.lg.jp/ | CKAN | ✕ 통계만 | CC-BY 4.0 |
| 山形 | https://www.pref.yamagata.jp/.../opendata/ | 정적HP | △ 테마별 CSV | CC-BY 4.0 |
| 福島 | https://www.pref.fukushima.lg.jp/sec/11045a/open-data-kanko.html | 정적HP/PDF | ✕ 대부분 PDF | 규약(상업가) |

### 3.2 간토

| 현 | 포털 URL | 플랫폼 | 관광 POI | 라이선스(상업) |
| --- | --- | --- | --- | --- |
| 茨城 | https://www.ibaraki-opendata.jp/ | 독자CMS/CSV | △ 빈약 | CC-BY 4.0 |
| 栃木 | https://odcs.bodik.jp/090000/ | BODIK | △ GIS분산 | CC-BY |
| 群馬 | https://toukei.pref.gunma.jp/ | 통계포털/비CKAN | ✕ 사실상 부재 | 개별 |
| 埼玉 | https://opendata.pref.saitama.lg.jp/ | dataeye | ○ 運輸·観光 155 | 자유(상업가) |
| 千葉 | https://opendata.pref.chiba.lg.jp/ | dataeye | ○ 관광시설·이벤트 | 자유(상업가) |
| 東京 | https://catalog.data.metro.tokyo.lg.jp/ | CKAN | ○ 観光施設(구별) | CC-BY 4.0 |
| 神奈川 | https://catalog.opendata.pref.kanagawa.jp/ | CKAN | ✕ 현 카탈로그 빈약 | 상업가 |

### 3.3 주부

| 현 | 포털 URL | 플랫폼 | 관광 POI | 라이선스(상업) |
| --- | --- | --- | --- | --- |
| 新潟 | https://www.pref.niigata.lg.jp/site/opendata/ | 정적HP | △ 협회 분리 | CC-BY |
| 富山 | https://opendata.pref.toyama.jp/ | CKAN | ○ 観光 그룹 | CC-BY |
| 石川 | https://ishikawa-datapf.jp/ckan/ | CKAN | ○ 観光 그룹(시정촌) | CC-BY |
| 福井 | https://www.pref.fukui.lg.jp/doc/dx-suishin/opendata/ | 정적 | ○ 観光·그루메 29 | CC-BY 4.0 |
| 山梨 | https://www.pref.yamanashi.jp/opendata/catalog/ | 독자 | ○ 観光·스포츠 | CC-BY(일부 NC) |
| 長野 | https://odcs.bodik.jp/nagano/ | BODIK | ○ 観光施設(시정촌) | CC-BY |
| 岐阜 | https://gifu-opendata.pref.gifu.lg.jp/ | CKAN | ○ 観光施設一覧 | CC-BY |
| 静岡 | https://opendata.pref.shizuoka.jp/ | 독자+WebAPI | ◎ 観光 171·自治体標準 | CC-BY(일부 NC) |
| 愛知 | https://www.e-aichi.jp/opendata.html | eあいち+BODIK | ○ 観光施設 30+ | CC-BY(일부 NC-ND) |

### 3.4 간사이

| 부현 | 포털 URL | 플랫폼 | 관광 POI | 라이선스(상업) |
| --- | --- | --- | --- | --- |
| 三重 | https://odcs.bodik.jp/240001/ | BODIK | △ 통계 중심 | CC-BY 4.0 |
| 滋賀 | https://odcs.bodik.jp/shiga-pref/ | BODIK | ✕ 현본체 POI 없음 | CC-BY 4.0 |
| 京都 | https://odcs.bodik.jp/260002/ | BODIK | ◎ 観光施設一覧(수천건) | CC-BY 4.0 |
| 大阪 | https://odcs.bodik.jp/270008/ | BODIK | ○ 観光施設一覧 | CC-BY 4.0 |
| 兵庫 | https://web.pref.hyogo.lg.jp/opendata/ | 독자PHP | ○ 지역·관광 | CC-BY(일부 NC/ND) |
| 奈良 | https://www.pref.nara.lg.jp/n026/44954.html | 정적HP | △ 망라 POI 없음 | CC-BY(일부) |
| 和歌山 | https://odcs.bodik.jp/300004/ | BODIK | ○ 観光施設 18 | CC-BY 4.0 |

### 3.5 주고쿠·시코쿠

| 현 | 포털 URL | 플랫폼 | 관광 POI | 라이선스(상업) |
| --- | --- | --- | --- | --- |
| 鳥取 | https://odp-pref-tottori.tori-info.co.jp/ | 독자(tori-info) | ○ 観光施設·ポイント一覧 | CC-BY(소수 NC) |
| 島根 | https://shimane-opendata.jp/ | dataeye | ○ 観光 32 | CC계열(상업가) |
| 岡山 | https://okayama-pref.dataeye.jp/ | dataeye | ○ 観光施設(시정촌) | PDL/CC 혼재 |
| 広島 | https://hiroshima-opendata.dataeye.jp/ | dataeye | ○ 観光施設·스폿 | CC-BY 2.1 JP |
| 山口 | https://odcs.bodik.jp/yamaguchi/ | BODIK | ○ 観光施設一覧 풍부 | CC-BY |
| 徳島 | https://opendata.pref.tokushima.lg.jp/ | 독자+WebAPI | ◎ 観光施設一覧(추천셋) | CC-BY |
| 香川 | https://opendata.pref.kagawa.lg.jp/ | Shirasagi | △ 건수 미상 | 이차이용가 |
| 愛媛 | https://www.pref.ehime.jp/opendata-catalog/ | 독자+WebAPI | ○ 観光 + GeoJSON | CC-BY |
| 高知 | https://www.pref.kochi.lg.jp/opendata/top/ | 카탈로그 없음/파일 | △ 현HP 파일 | CC-BY 4.0 |

### 3.6 규슈·오키나와 (전부 BODIK)

| 현 | 포털 URL | 플랫폼 | 관광 POI | 라이선스(상업) |
| --- | --- | --- | --- | --- |
| 福岡 | https://odcs.bodik.jp/400009/ | BODIK | ✕ 팸플릿 수준 | CC-BY 4.0 |
| 佐賀 | https://odcs.bodik.jp/410004/ | BODIK | ✕ 통계·Wi-Fi | CC-BY 4.0 |
| 長崎 | https://odcs.bodik.jp/420000/ | BODIK | ○ 旅ネット 観光스폿 | CC-BY 4.0 |
| 熊本 | https://odcs.bodik.jp/430005/ | BODIK | ○ 観光施設一覧 | CC-BY 4.0 |
| 大分 | https://odcs.bodik.jp/440001/ | BODIK | △ 통계·교통 위주 | CC-BY 4.0 |
| 宮崎 | https://odcs.bodik.jp/450006/ | BODIK | ✕ 통계 위주 | CC-BY 4.0 |
| 鹿児島 | https://odcs.bodik.jp/460001/ | BODIK | ✕ 접속로그 통계 | CC-BY 4.0 |
| 沖縄 | https://odcs.bodik.jp/470007/ | BODIK | ○ 観光ポイント一覧 | CC-BY 4.0 |

## 4. 보완·특화 소스

| 소스 | URL | 용도 | 라이선스 |
| --- | --- | --- | --- |
| Wikidata | https://www.wikidata.org/ | 전국 POI 좌표·식별자(균일) | CC0(상업 무제약) |
| OpenStreetMap | https://www.openstreetmap.org/ | 전국 tourism POI(고밀도) | ODbL(상업가, 파생DB ShareAlike→격리) |
| 大分 관광데이터카탈로그 | https://oita-tourism-data-catalog.com/ | 오이타 관광 데이터(API성) | 약관 미확인(별도 확인) |
| 北陸 TIFDATA | https://tifdata.jp/ | 北陸(富山·石川·福井) 관광 이동·소비 | 별도 확인 |
| 沖縄오픈데이터플랫폼 | okinawa-dpf(전 시정촌 대시보드) | 오키나와 관광·통계 | 별도 확인 |

## 5. 취득 우선순위 (효율 × 관광 POI 풍부도)

1. **e-Govデータポータル·BODIK API**로 観光施設 횡단 수집 — 16현+를 한 커넥터로.
2. dataeye·독자 CKAN(東京·静岡·徳島·愛媛·岐阜) — POI 풍부, WebAPI 보유.
3. Shirasagi·정적HP(北海道·山形·福井 등) — CSV 개별 수집.
4. POI 공백 현(秋田·福島·群馬·滋賀·佐賀·宮崎·鹿児島 등)은 Wikidata(CC0)·OSM로 보완.
5. 운영시간·입장료는 오픈데이터에 거의 없음 → 허가 기반 표적 보강.

## 6. 참고

- 라이선스 정밀 분석은 [japan_data_source_license_investigation_report.md](./japan_data_source_license_investigation_report.md) 참조.
- 본 디렉터리의 URL·플랫폼은 2026-06 기준 직접 확인(신뢰도: 높음). 관광 POI 보유도·건수는 일부 추정(신뢰도: 중간) — 실제 수집 전 각 포털에서 `観光施設` 데이터셋 유무를 재확인할 것.
