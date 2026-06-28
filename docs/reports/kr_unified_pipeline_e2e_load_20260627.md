# KR Unified Pipeline - E2E Load 실행 보고서

## 실행 요약

| 항목 | 값 |
|---|---|
| 실행 일시 | 2026-06-27 |
| Lambda 함수 | `kr-unified-pipeline` |
| 명령 | `load` (S3 → DynamoDB) |
| S3 소스 버킷 | `lovv-data-pipeline-dev-925273580929` |
| S3 프리픽스 | `processed/KR/details/20260609/passed/` |
| 대상 DynamoDB 테이블 | `TourKoreaDomainDataV2` |
| 실행 시간 | **33.46초** |
| 상태 코드 | **200 (성공)** |

## 적재 결과

| 메트릭 | 값 |
|---|---|
| S3에서 읽은 총 아이템 | **4,291** |
| DynamoDB 적재 성공 | **4,291** |
| DynamoDB 적재 실패 | **0** |
| 실패율 | **0%** |

## 소스 데이터 구성

- **인제스트 날짜**: 2026-06-09
- **소스 파일 수**: 40개 도시 JSON 파일
- **총 소스 크기**: ~7.2MB
- **도시 목록**: Andong, Bonghwa, Cheongdo, Cheongsong, Cheorwon, Chilgok, Chuncheon, Donghae, Gangneung, Gimcheon, Goryeong, Goseong, Gumi, Gyeongju, Gyeongsan, Hoengseong, Hongcheon, Hwacheon, Inje, Jeongseon, Mungyeong, Pohang, Pyeongchang, Samcheok, Sangju, Seongju, Sokcho, Taebaek, Uiseong, Uljin, Ulleung, Wonju, Yanggu, Yangyang, Yecheon, Yeongcheon, Yeongdeok, Yeongju, Yeongwol, Yeongyang

## 인프라 상태

### DynamoDB TourKoreaDomainDataV2

| 항목 | 값 |
|---|---|
| 상태 | ACTIVE |
| 빌링 모드 | PAY_PER_REQUEST |
| Point-in-Time Recovery | 활성화 |
| 총 아이템 수 | 4,291 |
| GSI | CityDomainIndex, ProvinceDomainIndex, EntityTypeDomainIndex, FestivalMonthIndex |

### Lambda kr-unified-pipeline

| 항목 | 값 |
|---|---|
| 상태 | Active |
| 런타임 | Python 3.12 |
| 핸들러 | `kr_unified_pipeline.handlers.pipeline_handler.handler` |
| 타임아웃 | 900초 (15분) |
| 메모리 | 1024MB |
| 지원 명령 | `load`, `vector-build`, `e2e`, `preprocess` |

## 지원되는 실행 모드

### 1. Load (S3 → DynamoDB)
```json
{
  "command": "load",
  "bucket": "lovv-data-pipeline-dev-925273580929",
  "ingest_date": "20260609",
  "table_name": "TourKoreaDomainDataV2"
}
```

### 2. Vector Build (DynamoDB → S3 Vectors)
```json
{
  "command": "vector-build",
  "table_name": "TourKoreaDomainDataV2",
  "rebuild_mode": "full"
}
```

### 3. E2E (Load + Vector Build)
```json
{
  "command": "e2e",
  "bucket": "lovv-data-pipeline-dev-925273580929",
  "ingest_date": "20260609",
  "table_name": "TourKoreaDomainDataV2",
  "rebuild_mode": "full"
}
```

### 4. Preprocess (Wikipedia + TourAPI 수집)
```json
{
  "command": "preprocess",
  "stages": ["wikipedia", "tourapi-region", "tourapi-detail"],
  "province_id": "KR-42"
}
```

## 다음 단계

1. **Vector Build 실행**: `vector-build` 명령으로 DynamoDB → S3 Vectors 인덱스 재빌드
2. **전국 확장**: 나머지 도시 데이터가 전처리되면 동일 파이프라인으로 적재
3. **모니터링**: CloudWatch Logs `/aws/lambda/kr-unified-pipeline` 로그 그룹에서 실행 이력 확인

## Lambda 응답 원본

```json
{
  "statusCode": 200,
  "summary": {
    "command": "load",
    "table_name": "TourKoreaDomainDataV2",
    "bucket": "lovv-data-pipeline-dev-925273580929",
    "ingest_date": "20260609",
    "execution_time_seconds": 33.46,
    "load": {
      "s3_files_read": 4291,
      "loaded": 4291,
      "load_failed": 0,
      "failures": []
    },
    "s3_files_read": 4291,
    "records_loaded": 4291,
    "vectors_upserted": 0,
    "errors": []
  }
}
```
