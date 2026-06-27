# Exclude Restaurants from Collection Bugfix Design

## Overview

The Tour API data collection pipeline (`tour_api_region_detail_acquisition.py`) unnecessarily collects restaurant records (contenttypeid=39) because `_filter_records` only checks category codes (`lclsSystm3`/`cat3`) against the theme mapping without verifying `contenttypeid`. The "미식·노포" theme in `theme_mapping.json` maps 21 FD-prefixed restaurant category codes (all with `contentTypeId: "39"`), causing these records to pass the filter. For each restaurant that passes, two expensive API calls (detailCommon2 + detailIntro2) are made, wasting API quota. The downstream `domain_preprocess.py` then classifies them as "excluded" anyway via `_classify_domain`. The fix adds a contenttypeid check in `_filter_records` to reject contenttypeid=39 records early, avoiding wasted API calls and storage.

## Glossary

- **Bug_Condition (C)**: A Tour API record has contenttypeid "39" (restaurant) AND its category code matches an entry in the theme map — causing it to incorrectly pass the filter
- **Property (P)**: Records with contenttypeid "39" shall be excluded during `_filter_records`, preventing downstream API calls and storage
- **Preservation**: All non-restaurant records (contenttypeid 12, 14, 15, 28) that currently pass the filter must continue to pass unchanged
- **`_filter_records`**: The function in `crawling/KR/tour_api_region_detail_acquisition.py` that filters raw API list results by category code before detail fetching
- **`_classify_domain`**: The function in `src/kr_details_pipeline/domain_preprocess.py` that classifies records by contenttypeid, returning "excluded" for 39
- **`theme_mapping.json`**: Reference file at `.cache/tour_api_korea_repo/data/theme_mapping.json` mapping category codes to themes, including 21 FD-prefixed codes under "미식·노포" with contentTypeId "39"
- **contenttypeid**: Tour API field identifying content type — 12 (관광지), 14 (문화시설), 15 (축제/공연/행사), 28 (레저), 39 (음식점)

## Bug Details

### Bug Condition

The bug manifests when a Tour API record has a category code (lclsSystm3/cat3) that matches an FD-prefixed entry in theme_mapping.json under the "미식·노포" theme. The `_filter_records` function checks only the category code against the theme map and does not verify the record's `contenttypeid`. Since all 21 FD-prefixed codes have `contentTypeId: "39"`, restaurant records pass the filter and trigger expensive detail API calls.

**Formal Specification:**
```
FUNCTION isBugCondition(record)
  INPUT: record of type dict[str, Any] (Tour API list response item)
  OUTPUT: boolean
  
  code := record.get("lclsSystm3") OR record.get("cat3") OR ""
  theme := theme_map.get(code)
  
  RETURN record.get("contenttypeid") == "39"
         AND theme IS NOT None
         AND theme NOT IN excluded_theme_names
         AND record.get("lclsSystm1") != "C01"
END FUNCTION
```

### Examples

- **Record with code "FD010100" (관광식당) and contenttypeid "39"**: Currently passes filter (assigned theme "미식·노포"), should be excluded
- **Record with code "FD050100" (카페) and contenttypeid "39"**: Currently passes filter, should be excluded
- **Record with code "HS010100" (고궁) and contenttypeid "12"**: Correctly passes filter → no change
- **Record with code "FD030600" (기타간이음식) and contenttypeid "39"**: Would be excluded by `_should_exclude` in `_build_theme_map` (name match), but if present in theme_map it currently passes filter — should be excluded by contenttypeid check
- **Record with code "NA010100" and contenttypeid "12" but NOT in theme_map**: Correctly excluded (no theme match) → no change

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Records with contenttypeid "12" (관광지) that match theme_mapping.json must continue to pass filter and get detail fetching
- Records with contenttypeid "14" (문화시설) that match theme_mapping.json must continue to pass filter and get detail fetching
- Records with contenttypeid "15" (축제/공연/행사) that match festival_mapping.json must continue to pass filter and get detail fetching
- Records with contenttypeid "28" (레저) that match theme_mapping.json must continue to pass filter and get detail fetching
- Records with `lclsSystm1 == "C01"` (course content) must continue to be excluded
- Records whose category code does NOT appear in the theme map must continue to be excluded
- The `_assigned_theme` field assignment on passing records must continue to work correctly

**Scope:**
All inputs that do NOT have contenttypeid "39" should be completely unaffected by this fix. This includes:
- All records with contenttypeid "12", "14", "15", or "28"
- Records with no contenttypeid field
- Records excluded by other existing conditions (C01 course check, no theme match)

## Hypothesized Root Cause

Based on the bug description, the root cause is:

1. **Missing contenttypeid check in `_filter_records`**: The function at line 233 only checks:
   - `lclsSystm1 == "C01"` → exclude
   - Category code match in `theme_map` → include
   
   It never inspects `contenttypeid`, so any record with a matching category code passes regardless of content type.

2. **Overly broad theme mapping**: The `theme_mapping.json` file includes the "미식·노포" theme with 21 FD-prefixed restaurant codes. While `_build_theme_map` excludes some entries via `_should_exclude` (name-based filtering for "기타주점", "클럽", "기타간이음식"), most restaurant codes still end up in the built theme map.

3. **Design assumption mismatch**: The original design appears to have assumed that filtering by category code alone would be sufficient because only valid content types would have matching codes. However, the "미식·노포" theme creates a cross-content-type mapping where restaurant codes (contentTypeId=39) are included alongside attraction/culture codes.

4. **Late-stage exclusion is wasteful**: The downstream `domain_preprocess.py._classify_domain` correctly excludes contenttypeid=39, but by that point, two detail API calls have already been made per restaurant record.

## Correctness Properties

Property 1: Bug Condition - Restaurant Records Excluded at Filter Stage

_For any_ Tour API record where contenttypeid is "39" (restaurant), the fixed `_filter_records` function SHALL exclude the record from the filtered results, regardless of whether its category code matches an entry in the theme map.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Restaurant Records Unaffected

_For any_ Tour API record where contenttypeid is NOT "39" (i.e., "12", "14", "15", "28", or any other value), the fixed `_filter_records` function SHALL produce the same filtering result as the original function, preserving all existing inclusion/exclusion behavior for non-restaurant content types.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `crawling/KR/tour_api_region_detail_acquisition.py`

**Function**: `_filter_records` (line 233)

**Specific Changes**:
1. **Add contenttypeid exclusion check**: Add a condition at the top of the loop body (after the existing C01 check) that skips records where `contenttypeid == "39"`:
   ```python
   if str(record.get("contenttypeid") or "") == "39":
       continue
   ```

2. **Placement**: The check should be placed after the existing `lclsSystm1 == "C01"` exclusion and before the category code lookup, to short-circuit early and avoid unnecessary dictionary lookups.

3. **Define excluded content type constant** (optional improvement): Consider defining `EXCLUDED_CONTENT_TYPE_IDS = {"39"}` as a module-level constant for clarity and future extensibility. This makes it easy to exclude additional content types later if needed.

4. **No changes to `_build_theme_map`**: The theme map construction does not need modification. While "미식·노포" codes still exist in theme_mapping.json, they will never match at the filter stage because records with contenttypeid=39 are rejected first.

5. **No changes to downstream code**: `domain_preprocess.py._classify_domain` can keep its existing contenttypeid=39 exclusion as a safety net, but it will no longer receive restaurant records from the collection stage.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `_filter_records` with records containing contenttypeid "39" and FD-prefixed category codes matching the theme map. Run these tests on the UNFIXED code to observe that restaurant records incorrectly pass the filter.

**Test Cases**:
1. **Restaurant with matching FD code**: Record with contenttypeid="39" and lclsSystm3="FD010100" with theme_map containing "FD010100" → passes filter on unfixed code (will fail assertion that it should be excluded)
2. **Multiple restaurants in batch**: Multiple records with various FD codes and contenttypeid="39" → all pass filter on unfixed code
3. **Restaurant with cat3 fallback**: Record with contenttypeid="39", no lclsSystm3 but cat3="FD020100" → passes filter on unfixed code
4. **Restaurant with C01 course flag**: Record with contenttypeid="39" AND lclsSystm1="C01" → already excluded by existing check (confirms C01 check works independently)

**Expected Counterexamples**:
- Records with contenttypeid="39" and matching FD codes are included in filtered results
- Each such record would trigger 2 additional API calls (detailCommon2 + detailIntro2) downstream

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior (record excluded).

**Pseudocode:**
```
FOR ALL record WHERE isBugCondition(record) DO
  result := _filter_records_fixed([record], theme_map, excluded_theme_names)
  ASSERT result == []  // restaurant record must be excluded
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL record WHERE NOT isBugCondition(record) DO
  ASSERT _filter_records_original([record], theme_map, excluded_theme_names)
         == _filter_records_fixed([record], theme_map, excluded_theme_names)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (various contenttypeid values, category codes, lclsSystm1 values)
- It catches edge cases that manual unit tests might miss (e.g., empty contenttypeid, None values, unexpected type combinations)
- It provides strong guarantees that behavior is unchanged for all non-restaurant inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-restaurant records, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Attraction preservation**: Records with contenttypeid="12" and matching codes continue to pass filter after fix
2. **Culture facility preservation**: Records with contenttypeid="14" and matching codes continue to pass filter after fix
3. **Festival preservation**: Records with contenttypeid="15" and matching festival codes continue to pass filter after fix
4. **Leisure preservation**: Records with contenttypeid="28" and matching codes continue to pass filter after fix
5. **Non-matching code preservation**: Records with any contenttypeid but non-matching codes continue to be excluded after fix
6. **C01 course preservation**: Records with lclsSystm1="C01" continue to be excluded regardless of other fields

### Unit Tests

- Test `_filter_records` rejects records with contenttypeid="39" even when category code matches theme map
- Test `_filter_records` rejects contenttypeid="39" with both lclsSystm3 and cat3 fallback paths
- Test edge cases: contenttypeid="39" with empty code, contenttypeid="39" with C01 flag
- Test that non-restaurant records with matching codes still pass (contenttypeid 12, 14, 28)

### Property-Based Tests

- Generate random records with contenttypeid="39" and arbitrary category codes → assert all excluded from filter results
- Generate random records with contenttypeid in {"12", "14", "15", "28"} → assert same filter result as original function
- Generate random combinations of contenttypeid, lclsSystm3, cat3, and lclsSystm1 → assert fixed function matches original for all non-39 inputs

### Integration Tests

- Test full `collect_city_list` flow with mixed records (some contenttypeid=39, some not) → verify restaurant records don't appear in output attractions list
- Test that `collect_regions` with restaurant records in API response does not trigger detail API calls for those records
- Test end-to-end: records excluded at collection stage match what `domain_preprocess._classify_domain` would have excluded
