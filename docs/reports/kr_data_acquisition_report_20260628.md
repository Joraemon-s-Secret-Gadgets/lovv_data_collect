# KR 전국 관광 데이터 취득 보고서

## 취득 개요

| 항목 | 값 |
|---|---|
| 보고일 | 2026-06-28 |
| 취득 대상 | 대한민국 전국 관광 데이터 |
| 취득 범위 | 211개 도시 (17개 광역시/도) |
| 데이터 소스 | TourAPI KorService2, TourAPI DataLabService |
| 취득 기간 | 2026-06-25 (관광지/축제), 2026-06-28 (방문자 통계) |

## 데이터 소스별 취득 현황

### 1. TourAPI KorService2 — 관광지/축제 데이터

| 항목 | 값 |
|---|---|
| API | TourAPI 4.0 KorService2 (areaBasedList, detailCommon) |
| 취득일 | 2026-06-25 |
| 도시 수 | 211개 |
| 파일 수 | 211개 JSON |
| 총 용량 | 27.5MB |
| S3 경로 | `s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260625/` |
| entity types | attraction, festival |

**취득 내역:**

| entity_type | 취득 레코드 수 | 설명 |
|---|---|---|
| attraction | ~5,800 | 관광지, 문화시설, 레포츠 |
| festival | ~500 | 축제/행사 |
| city metadata | 211 | 도시 기본 정보 |
| **합계** | **~6,500+** | |

**광역시/도별 분포:**

| 광역시/도 | 도시 수 | 비고 |
|---|---|---|
| 서울특별시 | 25 | 구 단위 |
| 부산광역시 | 16 | 구 단위 |
| 대구광역시 | 8 | 구/군 |
| 인천광역시 | 10 | 구/군 |
| 광주광역시 | 5 | 구 단위 |
| 대전광역시 | 5 | 구 단위 |
| 울산광역시 | 5 | 구/군 |
| 세종특별자치시 | 1 | 시 단위 |
| 경기도 | 31 | 시/군 |
| 강원특별자치도 | 18 | 시/군 |
| 충청북도 | 12 | 시/군 |
| 충청남도 | 15 | 시/군 |
| 전북특별자치도 | 14 | 시/군 |
| 전라남도 | 22 | 시/군 |
| 경상북도 | 23 | 시/군 |
| 경상남도 | 18 | 시/군 |
| 제주특별자치도 | 2 | 시 단위 |

### 2. TourAPI DataLabService — 방문자 통계

| 항목 | 값 |
|---|---|
| API | TourAPI DataLabService `locgoRegnVisitrDDList` |
| 취득일 | 2026-06-28 |
| 취득 도시 수 | 242개 시/군/구 |
| 기간 | 2025년 1월 ~ 12월 (12개월) |
| 로컬 파일 | `data/KR/visitor_statistics_2025.json` |
| signguCode 매핑 | 264개 (5자리 형식) |

**통계 항목:**

| 필드 | 설명 |
|---|---|
| locals_total | 현지인 방문 총수 |
| locals_daily_avg | 현지인 일평균 |
| out_of_town_total | 외지인 방문 총수 |
| out_of_town_daily_avg | 외지인 일평균 |
| foreigners_total | 외국인 방문 총수 |
| foreigners_daily_avg | 외국인 일평균 |
| total_visitors | 전체 방문 총수 |
| total_daily_avg | 전체 일평균 |

### 3. 이미지 데이터

| 항목 | 값 |
|---|---|
| 소스 | TourAPI `firstimage` 필드 (CDN URL) |
| 다운로드 성공 | 6,246장 |
| 다운로드 실패 | 0 |
| 소스 이미지 없음 | 402 레코드 |
| 총 이미지 용량 | ~1.2GB |
| 적재 위치 | `s3://lovv-pipeline-images-dev-925273580929/images/KR/{city}/` |
| 이미지 형식 | JPG (다수), PNG, GIF |

## 적재 현황

### DynamoDB TourKoreaDomainDataV2

| entity_type | 아이템 수 |
|---|---|
| attraction | ~5,800 |
| festival | ~500 |
| city (metadata) | 211 |
| visitor_statistics | 2,904 |
| **합계** | **9,778** |

### S3 Vectors (kr-tour-domain-v1)

| 항목 | 값 |
|---|---|
| 벡터 수 | 7,073 |
| 임베딩 모델 | Amazon Titan Embed Text v2 (1024차원) |
| 벡터화 대상 | attraction, festival, city |
| 제외 | visitor_statistics, restaurant |

### S3 이미지 버킷

| 항목 | 값 |
|---|---|
| 버킷 | `lovv-pipeline-images-dev-925273580929` |
| 이미지 수 | 6,246+ |
| 도시 수 | 211 |
| 폴더 구조 | `images/KR/{CITY_NAME_EN}/{filename}.jpg` |

## 데이터 품질 평가

| 항목 | 결과 | 비고 |
|---|---|---|
| 관광지 취득율 | 100% (211/211 도시) | 전 도시 성공 |
| 축제 취득율 | 100% | |
| 이미지 적재율 | 94% (6,246/6,648) | 402건 소스 이미지 없음 |
| 방문자 통계 커버리지 | 92% (242/264 시군구) | 22개 시군구 API 데이터 부재 |
| 중복 데이터 | 없음 | 20260625 단일 소스 사용 |
| 벡터 검색 정확도 | ✅ 정상 | "강릉 바다 관광지" → 해변 5개 정확 반환 |

## API 키 사용 현황

| API | 키 수 | Rate Limit | 사용량 |
|---|---|---|---|
| TourAPI KorService2 | 5 | 1000/일 | ~500 호출 |
| TourAPI DataLabService | 5 | 1000/일 | ~12 호출 |

## 제약사항 및 알려진 이슈

1. **방문자 통계 PK 형식**: 한글 도시명 사용 (`CITY#종로구`) — 관광지 PK(`CITY#GANGNEUNG`, 영문 대문자)와 불일치. Join 시 별도 매핑 필요.
2. **DataLab signguCode**: API 5자리 코드와 raw 데이터의 `lDongSignguCd`(가변 길이)가 다른 체계. `signgu_codes.json`을 5자리로 수정 완료.
3. **20260625 raw에 visitor_statistics 미포함**: 수집 스크립트(`tour_api_city_detail_acquisition.py`)에 DataLab 호출이 통합되지 않은 상태에서 수집됨. 코드 수정 완료 (향후 재수집 시 자동 포함).
4. **Lambda 15분 타임아웃**: 벡터 빌드 시 9,000+개 아이템은 타임아웃 초과. 로컬 실행 또는 Step Functions 분할 필요.

## 향후 계획

1. **전국 211개 도시 재수집**: visitor_statistics 포함된 완전한 raw 데이터 생성
2. **Step Functions 자동화**: Transform → Image → Load → Vector 전체 흐름 자동 실행
3. **증분 업데이트**: 신규 관광지/축제 추가 시 증분 벡터 빌드
4. **이미지 CDN**: CloudFront 배포로 이미지 URL 서빙
