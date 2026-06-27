# KR Tour API 데이터 취득 보고서

## 1. 보고서 개요

- 보고서 작성일: 2026-06-25
- 대상 파이프라인: `crawling/KR/tour_api_region_detail_acquisition.py`
- 취득 대상: 한국 17개 광역시/도 관광지·문화시설·축제 데이터
- 원천 API: 한국관광공사 Tour API `areaBasedList2`, `searchFestival2`, `detailCommon2`, `detailIntro2`
- 로컬 산출물 기준 경로: `data/KR/details/*.json`
- S3 저장 경로: `s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260625/`

본 보고서는 2026-06-24 19:28:07부터 2026-06-25 07:53:15까지 생성된 KR 상세 JSON 산출물을 기준으로 데이터 취득 결과를 정리한다. 취득된 상세 JSON은 S3 Raw 영역에 적재 완료되었으며, 업로드 결과는 `data/KR/ingest/upload_results.jsonl`에 기록되어 있다.

## 2. 취득 결과 요약

| 항목 | 결과 |
| --- | ---: |
| 상세 JSON 파일 수 | 211개 |
| 로컬 상세 JSON 총 용량 | 26.26 MB |
| 포함 광역시/도 수 | 17개 |
| 최종 수집 콘텐츠 수 | 6,663건 |
| 관광지/문화시설 계열 | 6,335건 |
| 축제/행사 계열 | 328건 |
| 빈 산출물 파일 | 5개 |

빈 산출물 파일은 `bukjeju.json`, `cheongwon-gun.json`, `jinhae.json`, `masan.json`, `namjeju.json`이다. 해당 파일은 행정구역 통폐합 또는 Tour API 응답 부재로 인해 최종 콘텐츠가 없는 상태로 보존되었다.

## 3. 지역별 산출물 분포

| 지역 | 파일 수 |
| --- | ---: |
| 경기도 | 31 |
| 서울 | 23 |
| 전라남도 | 22 |
| 경상북도 | 21 |
| 경상남도 | 20 |
| 강원특별자치도 | 17 |
| 충청남도 | 15 |
| 전북특별자치도 | 14 |
| 충청북도 | 12 |
| 부산 | 12 |
| 인천 | 7 |
| 울산 | 5 |
| 대구 | 4 |
| 제주특별자치도 | 4 |
| 대전 | 2 |
| 광주 | 1 |
| 세종특별자치시 | 1 |

## 4. 콘텐츠 유형 분포

| contenttypeid | 의미 | 건수 |
| --- | --- | ---: |
| `12` | 관광지 | 5,797 |
| `14` | 문화시설 | 538 |
| `15` | 축제/행사 | 328 |

음식점 유형인 `contenttypeid=39`는 최종 상세 산출물에 포함되지 않았다. 수집 단계에서 음식점 레코드를 제외하여 불필요한 상세 API 호출과 저장을 줄이는 기준을 적용했다.

## 5. 테마 분포

| 테마 | 건수 |
| --- | ---: |
| 역사·전통 | 3,271 |
| 자연·트레킹 | 1,960 |
| 예술·감성 | 689 |
| 바다·해안 | 547 |
| 온천·휴양 | 160 |
| 미식·노포 | 36 |

`미식·노포` 테마는 남아 있지만, 해당 항목들은 음식점 `contenttypeid=39`가 아니라 관광지·문화시설 유형으로 분류된 콘텐츠이다.

## 6. 저장 및 S3 적재 결과

취득된 상세 JSON 211개는 S3 Raw 영역에 적재 완료되었다.

- S3 버킷: `lovv-data-pipeline-dev-925273580929`
- S3 Prefix: `raw/KR/details/20260625/`
- 업로드 결과 파일: `data/KR/ingest/upload_results.jsonl`
- 실패 목록 파일: `data/KR/ingest/failed_uploads.jsonl`

| 업로드 상태 | 건수 |
| --- | ---: |
| uploaded | 211 |
| failed | 0 |
| skipped | 0 |

대표 S3 key 예시는 다음과 같다.

- `raw/KR/details/20260625/ANDONG.json`
- `raw/KR/details/20260625/CHUNCHEON.json`
- `raw/KR/details/20260625/SEOGWIPO.json`
- `raw/KR/details/20260625/YUSEONG-GU.json`

업로드 결과 기준 총 적재 바이트는 27,536,569 bytes이며, `failed_uploads.jsonl`에는 실패 레코드가 없다.

## 7. 산출물 활용 기준

S3에 적재된 Raw JSON은 후속 전처리 및 도메인 분리 적재의 입력으로 사용한다.

1. S3 Raw 입력
   - `s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260625/{CITY}.json`
2. 전처리 대상 도메인
   - 관광지/문화시설: attraction 계열
   - 축제/행사: festival 계열
3. 제외 기준
   - 음식점 `contenttypeid=39`는 수집 단계에서 제외된 상태로 후속 파이프라인에 전달하지 않는다.

## 8. 확인 사항 및 후속 작업

- 전체 17개 광역시/도 기준 산출물은 생성되었고 S3 Raw 영역에 적재 완료되었다.
- 빈 산출물 5개는 행정구역 이력 또는 Tour API 응답 부재 가능성이 있으므로, 운영 적재 전 별도 검토 대상으로 남긴다.
- 후속 단계에서는 S3 Raw 데이터를 기준으로 `TourKoreaDomainData` 적재 payload를 생성하고, 도시별/테마별 검색 인덱스와 연결한다.
