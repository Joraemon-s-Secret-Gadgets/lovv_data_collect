# KR Nationwide Wikipedia Data Acquisition Report

## Summary

| Item | Value |
|------|-------|
| Date | 2026-06-26 |
| Scope | 전국 17개 시도, 229개 시군구 |
| Data Source | Korean Wikipedia (ko.wikipedia.org) |
| Pipeline | `crawling.KR.city_wikipedia_acquisition --all-provinces` |
| Duration | ~5 min |
| Status | ✅ Complete |

## Results

### Wikipedia Metadata Acquisition

| Metric | Count |
|--------|-------|
| Total municipalities processed | 229 |
| Newly acquired | 164 |
| Skipped (already collected) | 65 |
| Failed | 0 |
| Success rate | 100% |

### Output Files

| File | Size | Location |
|------|------|----------|
| `data/KR/cities.json` | 1,215,356 bytes | Local + S3 |
| `data/KR/prefectures.json` | 13,015 bytes | Local + S3 |

### S3 Upload

| Key | Status |
|-----|--------|
| `raw/KR/wikipedia/20260626/cities.json` | ✅ Uploaded |
| `raw/KR/wikipedia/20260626/prefectures.json` | ✅ Uploaded |
| Bucket | `lovv-data-pipeline-dev-925273580929` |

## Province-Level Breakdown

All 17 provinces processed successfully:

| Province ID | Province Name | Municipalities |
|-------------|---------------|----------------|
| KR-11 | 서울특별시 | 25 |
| KR-26 | 부산광역시 | 16 |
| KR-27 | 대구광역시 | 9 |
| KR-28 | 인천광역시 | 10 |
| KR-29 | 광주광역시 | 5 |
| KR-30 | 대전광역시 | 5 |
| KR-31 | 울산광역시 | 5 |
| KR-36 | 세종특별자치시 | 1 |
| KR-41 | 경기도 | 31 |
| KR-42 | 강원특별자치도 | 18 |
| KR-43 | 충청북도 | 11 |
| KR-44 | 충청남도 | 15 |
| KR-45 | 전북특별자치도 | 14 |
| KR-46 | 전라남도 | 22 |
| KR-47 | 경상북도 | 23 |
| KR-48 | 경상남도 | 18 |
| KR-50 | 제주특별자치도 | 2 |
| **Total** | | **229** |

## Data Quality

### CityRecord Fields Collected

Each CityRecord contains:
- `city_id`: Unique identifier (e.g., "KR-11-JONGNO")
- `city_name_ko`: Korean name
- `city_name_en`: English romanization
- `prefecture_id`: Province ISO code
- `location`: Province English name
- `latitude` / `longitude`: Coordinates (Wikipedia or Nominatim fallback)
- `description`: Wikipedia lead paragraph
- `geography_description`: Geography section text
- `climate_table`: Climate data (when available)
- `site_urls`: Official website URLs
- `field_status`: Per-field collection status
- `data_confidence`: "low" / "medium" / "high"

### Data Completeness Notes

- 대부분의 시군구에서 좌표, 설명, 기본 정보 정상 추출
- 기후표가 없는 시군구는 `STATUS_NEEDS_REVIEW`로 마킹
- Nominatim geocoding fallback 적용된 일부 소규모 지자체 존재

## Issues / Notes

1. `철원군` — Wikipedia 제목이 "철원군 (대한민국)"으로 disambiguation 포함 (북한 철원군과 구분)
2. `군위군` — 2023년 대구광역시로 편입, MUNICIPALITY_EN_MAP 및 target file 추가
3. 기존 강원·경북 65개 도시는 이미 수집된 데이터이므로 스킵됨 (incremental merge 작동 확인)

## Verification Commands

```bash
# Local check
python -c "import json; d=json.load(open('data/KR/cities.json')); print(len(d))"
# → 229

# S3 check
aws s3 ls s3://lovv-data-pipeline-dev-925273580929/raw/KR/wikipedia/20260626/
```

## Related Issues

- Main: #27 [kr-nationwide-data-reacquisition]
- Sub: #28 CLI 확장, #29 batch processing, #31 target coverage, #35 S3 upload
