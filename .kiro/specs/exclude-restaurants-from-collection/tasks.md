# Implementation Plan

## Overview

Bugfix implementation plan for excluding restaurant records (contenttypeid=39) from the `_filter_records()` function in the Tour API data collection pipeline. This follows the exploratory bugfix workflow: write exploration tests to confirm the bug, write preservation tests to protect existing behavior, implement the fix, and validate.

## Tasks

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Restaurant Records Pass Through Filter
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate contenttypeid="39" records are not excluded by `_filter_records`
  - **Scoped PBT Approach**: Scope the property to concrete failing cases — records with contenttypeid="39" and FD-prefixed category codes that match the theme map
  - Test file: `crawling/KR/tests/test_tour_api_region_detail_acquisition.py`
  - Add test: pass a record `{"contentid": "r1", "contenttypeid": "39", "lclsSystm3": "FD010100"}` with theme_map `{"FD010100": "미식·노포"}` to `_filter_records()`
  - Assert the result is empty (record excluded)
  - Also test with `cat3` fallback: `{"contentid": "r2", "contenttypeid": "39", "cat3": "FD050100"}` with theme_map `{"FD050100": "미식·노포"}`
  - Assert the result is empty (record excluded)
  - Also test batch scenario: multiple contenttypeid="39" records with different FD codes → all excluded
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (records are included instead of excluded — this confirms the bug exists)
  - Document: "contenttypeid=39 records with valid FD-prefixed theme codes pass through _filter_records() because there is no contenttypeid-level exclusion check"
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Restaurant Records Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `crawling/KR/tests/test_tour_api_region_detail_acquisition.py`
  - Observe: `_filter_records([{"contentid": "a1", "contenttypeid": "12", "lclsSystm3": "HS010100"}], {"HS010100": "역사·전통"}, set())` returns 1 record with `_assigned_theme="역사·전통"` on unfixed code
  - Observe: `_filter_records([{"contentid": "c1", "contenttypeid": "14", "lclsSystm3": "CT010100"}], {"CT010100": "예술·감성"}, set())` returns 1 record on unfixed code
  - Observe: `_filter_records([{"contentid": "f1", "contenttypeid": "15", "lclsSystm3": "EV010100"}], {"EV010100": "예술·감성"}, set())` returns 1 record on unfixed code
  - Observe: `_filter_records([{"contentid": "s1", "contenttypeid": "28", "lclsSystm3": "SP010100"}], {"SP010100": "자연·트레킹"}, set())` returns 1 record on unfixed code
  - Observe: `_filter_records([{"contentid": "x1", "contenttypeid": "12", "lclsSystm1": "C01", "lclsSystm3": "HS010100"}], {"HS010100": "역사·전통"}, set())` returns 0 records (existing C01 exclusion)
  - Observe: `_filter_records([{"contentid": "n1", "contenttypeid": "12", "lclsSystm3": "NA010100"}], {"HS010100": "역사·전통"}, set())` returns 0 records (code not in theme_map)
  - Write tests asserting these observed behaviors are preserved for all non-restaurant content types
  - Verify `_assigned_theme` field is correctly set on passing records
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3. Fix: Exclude restaurant records (contenttypeid=39) from `_filter_records()`

  - [ ] 3.1 Implement the fix
    - Add `EXCLUDED_CONTENT_TYPE_IDS = {"39"}` constant near module-level constants in `crawling/KR/tour_api_region_detail_acquisition.py`
    - Add contenttypeid guard clause in `_filter_records()` after the existing `lclsSystm1 == "C01"` check and before the category code lookup:
      ```python
      if str(record.get("contenttypeid") or "") in EXCLUDED_CONTENT_TYPE_IDS:
          continue
      ```
    - No signature changes, no new parameters required
    - Placement: after C01 check, before `code = str(record.get("lclsSystm3") or ...)` line
    - _Bug_Condition: isBugCondition(record) where record.get("contenttypeid") == "39" AND theme_map.get(code) is not None_
    - _Expected_Behavior: record excluded from filtered results, no detail API calls made_
    - _Preservation: Non-"39" records (contenttypeid 12, 14, 15, 28) continue to filter identically by lclsSystm1 and theme-map logic_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Restaurant Records Excluded
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (contenttypeid=39 records excluded)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Restaurant Records Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [ ] 4. Checkpoint — Ensure all tests pass
  - Run full test suite: `python -m pytest crawling/KR/tests/test_tour_api_region_detail_acquisition.py -v`
  - Ensure all tests pass, ask the user if questions arise

## Task Dependency Graph

```json
{
  "waves": [
    ["1", "2"],
    ["3.1"],
    ["3.2", "3.3"],
    ["4"]
  ]
}
```

## Notes

- Tasks 1 and 2 are independent and can be worked on in either order, but both must complete before task 3.
- The exploration test (task 1) is expected to FAIL on unfixed code — this is intentional and confirms the bug exists.
- The preservation tests (task 2) are expected to PASS on unfixed code — this captures the baseline behavior.
- After the fix (task 3.1), the exploration test should PASS and preservation tests should still PASS.
- The fix targets `crawling/KR/tour_api_region_detail_acquisition.py`, specifically the `_filter_records()` function.
- Test file: `crawling/KR/tests/test_tour_api_region_detail_acquisition.py`
