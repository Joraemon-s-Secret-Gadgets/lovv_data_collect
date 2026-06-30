# KR 20260630 데이터 전처리 및 Vector V2 적재 완료 보고서

## 1. 보고서 개요

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-06-30 |
| 대상 프로젝트 | `02_lovv_data_collect` |
| 대상 원천 데이터 | `raw/KR/details/20260629/` |
| 전처리 Lambda | `kr-pipeline-transform` |
| 적재 대상 DynamoDB | `TourKoreaDomainDataV2` |
| 적재 대상 Vector | `lovv-vector-dev` / `kr-tour-domain-v2` |
| processed prefix | `processed/KR/details/20260629/` |
| Vector manifest | `s3://lovv-data-pipeline-dev-925273580929/processed/KR/details/vector/manifests/latest.json` |

본 문서는 2026-06-29 KR 상세 raw 240개에 대한 전처리, DynamoDB V2 적재 상태, S3 Vector V2 적재 완료 상태를 정리한다. 기존 `kr_20260629_preprocessing_report.md`는 Vector가 비어 있던 시점의 예측 보고서였고, 본 문서는 실제 Vector 적재 완료 후 검증 결과를 반영한 완료 보고서다.

## 2. 최종 판단

전처리, DynamoDB V2 적재, Vector V2 적재는 완료로 판단한다.

| 판단 항목 | 결과 |
| --- | --- |
| 전처리 대상 raw detail | 240개 |
| `kr-pipeline-transform` 성공 | 240개 |
| `kr-pipeline-transform` 실패 | 0건 |
| `passed/` load-ready item | 8,010건 |
| DynamoDB V2 live item | 8,010건 |
| Vector export 대상 | 7,662건 |
| Vector unique key | 7,606개 |
| S3 Vector V2 live count | 7,606개 |
| Vector sample query | 성공 |
| Vector manifest 작성 | 완료 |

Vector count가 7,662가 아니라 7,606인 이유는 source item 7,662개 중 vector key가 중복되는 chunk 56개가 있었기 때문이다. S3 Vectors는 같은 key를 중복 저장하지 않으므로 완료 기준은 `unique_vector_key_count=7,606`이다.

## 3. 전처리 결과

`kr-pipeline-transform`은 2026-06-29 raw detail 240개를 모두 처리했다.

| 항목 | 값 |
| --- | ---: |
| Manifest record count | 240 |
| Lambda invoked | 240 |
| Lambda succeeded | 240 |
| Failed invocations | 0 |
| Duplicate city ids | 0 |
| Failed raw keys | 0 |

S3 산출물은 다음 prefix에 생성되었다.

| Prefix | JSON files |
| --- | ---: |
| `processed/KR/details/20260629/passed/` | 240 |
| `processed/KR/details/20260629/review/` | 240 |
| `processed/KR/details/20260629/failed/` | 240 |
| `processed/KR/details/20260629/quality/` | 240 |

## 4. DynamoDB V2 적재 상태

`TourKoreaDomainDataV2` live scan 결과는 `passed/` 산출물과 일치한다.

| Entity type | DynamoDB items |
| --- | ---: |
| `city_metadata` | 240 |
| `attraction` | 7,024 |
| `festival` | 398 |
| `visitor_statistics` | 348 |
| 합계 | 8,010 |

`visitor_statistics`는 DynamoDB에는 적재되어 있지만 Vector rebuild 대상에서는 제외된다.

## 5. Wikipedia 보강 상태

| 항목 | 값 |
| --- | ---: |
| City metadata | 240 |
| Wikipedia matched | 181 |
| Wikipedia missing | 59 |

`wiki_status=missing` 59건은 전처리 실패가 아니라 Wikipedia raw와 city key가 연결되지 않은 상태다. 후속 실사 기준으로 48건은 raw 후보가 있으나 `-GU`, `-GUN` 등 영문 key suffix 차이로 매칭되지 않았고, 11건은 raw 후보 자체가 없다.

Raw 후보가 없는 11개 key는 다음과 같다.

```text
BUK-GU
BUKJEJU
CHEONGWON-GUN
DONG-GU
GANGSEO-GU
JINHAE
JUNG-GU
MASAN
NAM-GU
NAMJEJU
SEO-GU
```

## 6. 이미지 S3 URL 치환 상태

| 항목 | 값 |
| --- | ---: |
| 관광지/축제 image 대상 | 7,422 |
| S3 URL 치환 완료 | 6,975 |
| 외부 image URL 잔존 | 0 |
| `source_image_url` 보존 | 6,975 |
| 원천 이미지 없음 | 447 |
| 이미지 다운로드/업로드 실패 | 0 |

이미지 버킷 검증 결과, 2026-06-29 13:00Z 이후 생성된 `images/KR/` 객체는 6,975개이며 총 크기는 2,009,551,566 bytes다.

## 7. Review 산출물 상태

`review/` prefix에는 1,202건이 분리되어 있다.

| Review queue | Count |
| --- | ---: |
| `source_review` | 1,184 |
| `location_review` | 18 |
| `classification_review` | 1 |

Review queue count 합계가 1,202보다 1건 많은 이유는 1개 record가 복수 queue를 가진 것으로 판단한다. Review record 자체는 1,202건이다.

| Entity type | Review records |
| --- | ---: |
| `excluded` | 1,184 |
| `attraction` | 16 |
| `festival` | 2 |
| 합계 | 1,202 |

## 8. Vector V2 적재 결과

Vector 적재는 DynamoDB V2의 `EntityTypeDomainIndex`에서 vectorizable item을 export한 뒤 Titan embedding과 S3 Vectors upsert를 수행했다.

| 항목 | 값 |
| --- | ---: |
| Export 대상 | 7,662 |
| `city_metadata` | 240 |
| `attraction` | 7,024 |
| `festival` | 398 |
| Chunks created | 7,662 |
| Duplicate chunk keys | 56 |
| Unique vector keys | 7,606 |
| S3 Vector live count | 7,606 |
| Embedding failed | 0 |
| Vector failed | 0 |

사용한 embedding model은 `amazon.titan-embed-text-v2:0`이고, manifest의 `index_text_mode`는 `rich`다.

## 9. Lambda 실행 결과와 우회 실행 사유

`kr-pipeline-loader` Lambda에 다음 payload로 `vector-build`를 직접 실행했다.

```json
{
  "command": "vector-build",
  "table_name": "TourKoreaDomainDataV2",
  "vector_bucket": "lovv-vector-dev",
  "index_name": "kr-tour-domain-v2",
  "rebuild_mode": "full"
}
```

하지만 현재 Lambda 구현은 7,662개 embedding을 순차 처리하므로 900초 timeout에 도달했다. `RequestResponse` 호출 과정에서 SDK retry로 4개 invoke가 시작되었고, CloudWatch에서 4개 모두 `Status: timeout`, `Duration: 900000.00 ms`로 종료된 것을 확인했다.

Vector 적재는 같은 repository의 `kr_vector_index` 모듈을 사용하는 로컬 병렬 runner로 완료했다. 로컬 runner는 DynamoDB export, chunk 생성, Titan embedding, S3 Vectors upsert 경로를 동일하게 사용하되 embedding을 병렬 처리해 Lambda timeout을 피했다.

## 10. Vector 검증

### Count 검증

| 검증 항목 | 값 |
| --- | ---: |
| Expected unique vector keys | 7,606 |
| `list-vectors` count | 7,606 |
| `list-vectors` pages | 16 |
| Count match | yes |

### Sample query 검증

검증 query는 다음 문장으로 수행했다.

```text
경주 문화유산 사찰 역사 관광지
```

Top result는 `GYEONGJU` 관광지 vector로 반환되었다.

| 항목 | 값 |
| --- | --- |
| Top key | `attraction#971032#0` |
| Top city | `GYEONGJU` |
| Top entity type | `attraction` |

## 11. Manifest

Vector 완료 manifest는 다음 두 위치에 작성했다.

```text
s3://lovv-data-pipeline-dev-925273580929/processed/KR/details/vector/manifests/20260630/kr-tour-domain-v2.json
s3://lovv-data-pipeline-dev-925273580929/processed/KR/details/vector/manifests/latest.json
```

Manifest 주요 값은 다음과 같다.

| Field | Value |
| --- | ---: |
| `items_exported` | 7,662 |
| `chunks_created` | 7,662 |
| `unique_vector_key_count` | 7,606 |
| `duplicate_chunk_key_count` | 56 |
| `vector_success_count` | 7,606 |
| `failed_count` | 0 |
| `list_vectors_verified_count` | 7,606 |

## 12. 남은 리스크와 후속 작업

| 항목 | 현재 상태 | 후속 작업 |
| --- | --- | --- |
| `kr-pipeline-loader` Lambda vector-build | Timeout | embedding 병렬화, Step Functions 분할, 또는 async batch worker로 개선 필요 |
| Wikipedia missing 59 | Review 필요 | suffix normalize 및 raw 후보 없는 11개 보강 여부 결정 |
| No source image 447 | Review 필요 | 이미지 없는 상태 허용 또는 대체 이미지 수집 정책 결정 |
| Review items 1,202 | Review 필요 | `source_review`, `location_review`, `classification_review`별 triage |
| Duplicate vector key 56 | 허용 가능 | 같은 key 덮어쓰기 정책이 의도된 것인지 확인 필요 |

## 13. 결론

20260629 KR 데이터 전처리는 완료되었다. `passed/` 기준 8,010개 item이 DynamoDB V2에 적재되어 있고, `visitor_statistics`를 제외한 vectorizable item은 S3 Vector V2에 7,606개 unique vector로 적재되어 있다.

현재 운영상 남은 핵심 작업은 데이터 재적재가 아니라 `kr-pipeline-loader`의 vector-build 실행 방식을 개선하는 것이다. 현 Lambda는 전체 nationwide vector rebuild를 단일 900초 실행 안에서 처리하기 어렵기 때문에, 병렬 embedding 또는 분할 실행 구조로 바꾸는 것이 필요하다.
