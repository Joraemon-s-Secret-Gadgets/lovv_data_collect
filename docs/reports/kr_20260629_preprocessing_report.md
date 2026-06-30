# KR 20260629 전처리 결과 및 적재 예측 보고서

## 1. 보고서 개요

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-06-29 |
| 대상 프로젝트 | `02_lovv_data_collect` |
| 대상 데이터 | `raw/KR/details/20260629/` |
| 실행 Lambda | `kr-pipeline-transform` |
| 실행 범위 | 240개 raw detail JSON 전체 |
| 산출 prefix | `processed/KR/details/20260629/` |
| DynamoDB 대상 | `TourKoreaDomainDataV2` |
| Vector 대상 | `lovv-vector-dev` / `kr-tour-domain-v2` |
| 결과 파일 | `.cache/kr_preprocess_20260629_lambda_results.json` |
| S3 summary | `s3://lovv-data-pipeline-dev-925273580929/processed/KR/details/20260629/quality/summary.json` |

본 문서는 2026-06-29 KR raw detail 240개를 `kr-pipeline-transform`으로 전처리한 결과와, 해당 산출물을 DynamoDB V2 및 S3 Vector V2로 넘겼을 때의 예상 적재량을 정리한다.

## 2. 최종 판단

전처리 자체는 성공으로 판단한다.

| 판단 항목 | 결과 |
| --- | --- |
| Lambda 실행 | 240개 전부 성공 |
| Lambda 실패 | 0건 |
| processed 산출물 | `passed/review/failed/quality` 각각 240개 생성 |
| DDB 적재 후보 | 8,010건 |
| Vector 후보 | 7,662건 |
| 이미지 S3 URL 치환 | 6,975건 |
| 외부 image URL 잔존 | 0건 |
| Wikipedia 매칭 | 181개 도시 matched, 59개 missing |
| 치명적 failed item | 0건 |

따라서 다음 단계는 raw 재취득이 아니라 `kr-pipeline-loader`의 `e2e` 또는 `vector-build` 실행이다.

## 3. 실행 환경

`kr-pipeline-transform`은 전체 실행 전에 이미지 다운로드가 포함된 처리 시간을 감안해 다음 설정으로 배포했다.

| 항목 | 값 |
| --- | --- |
| Runtime | `python3.12` |
| Timeout | `900` seconds |
| Memory | `1024` MB |
| `DYNAMODB_TABLE` | `TourKoreaDomainDataV2` |
| `PROCESSED_PREFIX` | `processed/KR/details` |
| `IMAGE_BUCKET` | `lovv-pipeline-images-dev-925273580929` |

Terraform 최종 검증 결과는 `No changes`였고, 실제 인프라가 configuration과 일치함을 확인했다.

## 4. 입력 데이터

| 입력 | 경로 또는 값 |
| --- | --- |
| Raw detail prefix | `s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260629/` |
| Raw detail manifest | `data/KR/ingest/20260629_resolved_details/raw_manifest.json` |
| Raw detail file count | 240 |
| Wikipedia city raw | `s3://lovv-data-pipeline-dev-925273580929/raw/KR/wikipedia/20260629/cities.json` |
| Image output bucket | `s3://lovv-pipeline-images-dev-925273580929/images/KR/` |

전처리 Lambda는 detail raw를 도시 단위로 읽고, 같은 ingest date의 Wikipedia city raw를 매칭한 뒤, 관광지/축제 이미지 URL을 이미지 버킷의 S3 HTTPS URL로 치환한다.

## 5. 전처리 실행 결과

전체 runner 집계는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| Manifest record count | 240 |
| Lambda invoked | 240 |
| Lambda succeeded | 240 |
| Failed invocations | 0 |
| Duplicate city ids | 0 |
| Failed raw keys | 0 |

S3 산출물 개수는 다음과 같다.

| Prefix | JSON files |
| --- | ---: |
| `processed/KR/details/20260629/passed/` | 240 |
| `processed/KR/details/20260629/review/` | 240 |
| `processed/KR/details/20260629/failed/` | 240 |
| `processed/KR/details/20260629/quality/` | 240 |

## 6. Passed 산출물 기준 도메인 분포

`passed/`의 실제 records를 재조회한 결과는 다음과 같다.

| Entity type | Passed records |
| --- | ---: |
| `city_metadata` | 240 |
| `attraction` | 7,024 |
| `festival` | 398 |
| `visitor_statistics` | 348 |
| 합계 | 8,010 |

전처리 summary의 전체 load candidate는 8,028건이지만, downstream load 대상인 `passed/`에는 8,010건만 포함된다. 나머지는 review 산출물에서 품질 확인 대상으로 분리된다.

## 7. Wikipedia 보강 결과

| 항목 | 값 |
| --- | ---: |
| Wiki matched | 181 |
| Wiki missing | 59 |
| City metadata records | 240 |

`wiki_status=matched`인 city metadata에는 `source_url`, `description`, `geography_description`, `site_urls` 등 Wikipedia 보강 필드가 포함된다. `wiki_status=missing`은 전처리 실패가 아니라 현재 매칭 키 기준으로 Wikipedia city raw와 연결되지 않은 상태를 의미한다.

## 8. 이미지 S3 치환 결과

| 항목 | 값 |
| --- | ---: |
| S3 URL로 치환된 image records | 6,975 |
| `source_image_url` 보존 records | 6,975 |
| 외부 image URL 잔존 | 0 |
| 이미지 다운로드/업로드 실패 | 0 |
| 원천 이미지 없음 | 447 |
| 이미지 review entries | 447 |
| 2026-06-29 13:00Z 이후 이미지 업로드 객체 | 6,975 |
| 업로드 총 크기 | 2,009,551,566 bytes |

S3 URL은 다음 형태로 생성된다.

```text
https://lovv-pipeline-images-dev-925273580929.s3.amazonaws.com/images/KR/{CITY}/{IMAGE_NAME}_1.{ext}
```

원천 이미지가 있는 레코드는 `image_url`이 S3 HTTPS URL로 치환되고, 원본 URL은 `source_image_url`로 보존된다. 원천 이미지가 없는 447건은 `image_status=needs_review`로 남는다.

## 9. DynamoDB 적재 예측

`kr-pipeline-loader`가 `processed/KR/details/20260629/passed/`를 읽으면 DynamoDB V2에 적재될 예상 item 수는 8,010건이다.

| 항목 | 값 |
| --- | ---: |
| 예상 DDB write 대상 | 8,010 |
| 현재 `TourKoreaDomainDataV2` scan 합산 | 8,010 |
| 예상/현재 count 일치 | yes |

작성 시점 기준 `TourKoreaDomainDataV2`의 scan count 합산이 8,010건으로 관측되었다. 이는 현재 전처리 `passed/` 산출물의 record count와 일치한다.

## 10. Vector 적재 예측

Vector rebuild는 `visitor_statistics`를 제외해야 한다. 따라서 현재 `passed/` 기준 vector 후보는 다음과 같다.

| Entity type | Vector candidate |
| --- | ---: |
| `city_metadata` | 240 |
| `attraction` | 7,024 |
| `festival` | 398 |
| `visitor_statistics` | 0 |
| 예상 vector total | 7,662 |

작성 시점 기준 `lovv-vector-dev / kr-tour-domain-v2`의 `list-vectors` 결과는 empty였다. 따라서 아직 Vector V2 적재 완료 상태는 아니며, `kr-pipeline-loader`의 `vector-build` 또는 `e2e` 실행 후 약 7,662개 vector upsert가 예상된다.

## 11. 콘솔 실행 명령

전처리는 이미 240개 전체 완료되었으므로, AWS Console에서 다음으로 실행할 Lambda는 `kr-pipeline-loader`이다.

```json
{
  "command": "e2e",
  "bucket": "lovv-data-pipeline-dev-925273580929",
  "ingest_date": "20260629",
  "table_name": "TourKoreaDomainDataV2",
  "vector_bucket": "lovv-vector-dev",
  "index_name": "kr-tour-domain-v2",
  "rebuild_mode": "full"
}
```

이미 DynamoDB count가 8,010건으로 일치하는 상태에서 Vector만 재생성하려면 아래 이벤트를 사용할 수 있다.

```json
{
  "command": "vector-build",
  "table_name": "TourKoreaDomainDataV2",
  "vector_bucket": "lovv-vector-dev",
  "index_name": "kr-tour-domain-v2",
  "rebuild_mode": "full"
}
```

## 12. 검증 증거

| 검증 항목 | 결과 |
| --- | --- |
| Targeted tests | `31 passed` |
| Python compile | 통과 |
| Terraform validate | 성공 |
| Terraform final plan | `No changes` |
| S3 `passed/` records 재조회 | 8,010 records |
| S3 image URL 검증 | 6,975 / non-S3 0 |
| Image bucket 객체 수 검증 | 6,975 objects |
| DynamoDB V2 count 합산 | 8,010 |
| S3 Vector V2 현재 상태 | empty |

## 13. 남은 리스크와 후속 작업

| 항목 | 상태 | 후속 작업 |
| --- | --- | --- |
| Wikipedia missing 59 | Review 필요 | 매칭 키 보강 또는 Wikipedia raw 보강 여부 판단 |
| No source image 447 | Review 필요 | 대체 이미지 수집 또는 이미지 없는 상태 허용 여부 결정 |
| Review items 1,202 | Review 필요 | `review/` prefix에서 품질 사유별 triage |
| Vector V2 empty | 미완료 | `kr-pipeline-loader` `vector-build` 또는 `e2e` 실행 |
| Vector 결과 검증 | 미완료 | build 후 `list-vectors`, manifest, sample query 확인 |

## 14. 결론

20260629 KR 전처리는 운영 적재 후보 생성 관점에서 완료되었다. `passed/` 산출물은 240개 도시 파일, 8,010개 load-ready item으로 구성되며, Wikipedia 보강과 이미지 S3 URL 치환이 반영되어 있다.

다음 완료 기준은 `kr-tour-domain-v2`에 약 7,662개 vector가 적재되고, sample query로 city/attraction/festival 검색 품질을 확인하는 것이다.
