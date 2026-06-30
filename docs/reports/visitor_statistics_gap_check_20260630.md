# Visitor Statistics Gap Check - 2026-06-30

## Conclusion

At investigation time, `visitor_statistics` was partially missing from the live `TourKoreaDomainDataV2` table.

The original live state had valid key shape for the rows that existed, but only 29 cities had 2025 monthly visitor statistics. The V2 city set had 240 `city_metadata` rows, so 211 city PKs had no visitor statistics rows.

This is not a vector-index issue. `visitor_statistics` is intentionally excluded from S3 Vector rebuilds. The gap is in the DataLab raw/merge/preprocessing path before DynamoDB load.

Remediation was completed on 2026-06-30. The live table now has 2,820 `visitor_statistics` rows, covering 235 cities x 12 months. Five legacy/obsolete city PKs still have no matching DataLab source in the local file and remain unresolved.

## Live DynamoDB Evidence

Table: `TourKoreaDomainDataV2`

### Before Remediation

Entity counts from `EntityTypeDomainIndex`:

| entity_type | live count |
|---|---:|
| `city_metadata` | 240 |
| `attraction` | 7,024 |
| `festival` | 398 |
| `visitor_statistics` | 348 |
| `city` | 0 |

Visitor statistics shape:

| check | result |
|---|---:|
| `visitor_statistics` rows | 348 |
| distinct city PKs with stats | 29 |
| rows per loaded city | 12 |
| month coverage | `202501` - `202512`, 29 rows each |
| rows with `gsi_sk` | 0 |
| rows with non-`STAT#` SK | 0 |
| rows where `domain_sort_key != SK` | 0 |

Expected rows if every current V2 city had 2025 monthly stats:

| baseline | expected | actual | gap |
|---|---:|---:|---:|
| 240 current `city_metadata` rows x 12 months | 2,880 | 348 | 2,532 |

### After Remediation

Entity counts from `EntityTypeDomainIndex`:

| entity_type | live count |
|---|---:|
| `visitor_statistics` | 2,820 |

Post-remediation visitor statistics shape:

| check | result |
|---|---:|
| `visitor_statistics` rows | 2,820 |
| distinct city PKs with stats | 235 |
| rows per loaded city | 12 |
| rows with `gsi_sk` | 0 |
| rows with non-`STAT#` SK | 0 |
| rows where `domain_sort_key != SK` | 0 |

Residual gap:

| baseline | expected | actual | gap |
|---|---:|---:|---:|
| 240 current `city_metadata` rows x 12 months | 2,880 | 2,820 | 60 |

The remaining 60 rows correspond to five city PKs without matching DataLab source:

- `CITY#BUKJEJU`
- `CITY#CHEONGWON-GUN`
- `CITY#JINHAE`
- `CITY#MASAN`
- `CITY#NAMJEJU`

## Source/Processed Evidence

Local DataLab file:

| file | city keys | monthly records |
|---|---:|---:|
| `data/KR/visitor_statistics_2025.json` | 271 | 3,252 |

S3 DataLab raw contract:

| prefix | status |
|---|---|
| `s3://lovv-data-pipeline-dev-925273580929/raw/KR/datalab/20260629/visitor_statistics_2025.json` | uploaded on 2026-06-30 |

Processed aggregate summary:

| object | visitor_statistics |
|---|---:|
| `processed/KR/details/20260629/quality/summary.json` | 348 |

Sample city checks:

| city | raw detail visitor_statistics | processed visitor_statistics |
|---|---:|---:|
| `ANDONG` | absent | 0 |
| `BUK-BUSAN` | present | 12 |

This shows the current loader did not drop valid rows after preprocessing. Instead, only raw detail payloads that already contained `visitor_statistics` produced monthly stats. Cities whose raw detail payload lacked `visitor_statistics` produced zero stat rows.

## Interpretation

The current live state is internally consistent for loaded visitor-stat rows:

- `SK=STAT#{YYYYMM}` is correct.
- `domain_sort_key=STAT#{YYYYMM}` is correct.
- `gsi_sk` is correctly absent.
- Existing stat cities each have all 12 months.

The missing part is coverage:

- Only 29 of 240 current V2 city PKs have stats.
- 211 current V2 city PKs have no stats.
- The local DataLab file contains broader coverage, but it was not available at the expected S3 raw DataLab prefix and was not joined into most detail payloads during the live preprocessing run.

## Recommended Next Step

Do not change the vector Lambda for this gap.

Completed remediation:

1. Added `src/kr_details_pipeline/visitor_statistics_backfill.py` to build missing monthly statistic rows from the local DataLab file.
2. Added `scripts/backfill_visitor_statistics.py` with dry-run by default and guarded `--apply` writes.
3. Added tests for Korean city-name lookup and skip behavior for already-loaded disambiguated city rows.
4. Uploaded `data/KR/visitor_statistics_2025.json` to the DataLab raw S3 contract path.
5. Inserted 2,472 missing DynamoDB rows with conditional `attribute_not_exists(PK) AND attribute_not_exists(SK)` protection.

Remaining work for full 240-city coverage:

1. Decide whether obsolete/merged legacy cities `BUKJEJU`, `NAMJEJU`, `CHEONGWON-GUN`, `JINHAE`, and `MASAN` should be retained as active city metadata.
2. If retained, acquire or map replacement DataLab rows for those five city PKs.
3. If not retained, move those city metadata rows to review/deprecated handling rather than trying to synthesize statistics.

Do not use S3 Vector rebuild as the fix path; `visitor_statistics` is intentionally excluded from vector indexing.
