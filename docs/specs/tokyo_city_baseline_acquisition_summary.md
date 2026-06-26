# Spec Summary: Tokyo City Baseline Acquisition

This summary is not authoritative. Use it only to find relevant Full Spec sections.

## Source of Truth

- Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Review Gate: `docs/reports/japan_attraction_festival_spec_review.md`
- Implementation Subtasks: `docs/specs/TASK1_SUBTASKS.md`

## Section Map

- Objective: `docs/specs/tokyo_city_baseline_acquisition_spec.md#objective`
- Requirements: `docs/specs/tokyo_city_baseline_acquisition_spec.md#requirements`
- Design: `docs/specs/tokyo_city_baseline_acquisition_spec.md#design`
- Acceptance Criteria: `docs/specs/tokyo_city_baseline_acquisition_spec.md#acceptance-criteria`
- Verification: `docs/specs/tokyo_city_baseline_acquisition_spec.md#verification`
- Risks: `docs/specs/tokyo_city_baseline_acquisition_spec.md#risks`

## Coverage

- Tokyo 62-municipality scope: full
- 23 wards plus 39 other municipalities: full
- Japanese-name completion from KO langlinks: full
- Rerun-safe merge behavior: full
- Live Wikipedia reacquisition procedure: partial, requires implementation approval before running
- Non-Tokyo Kanto City expansion: not covered
- Attraction/Festival acquisition: not covered and explicitly blocked
- OSM/Wikidata POI fallback: not covered in this City baseline phase

## Current Known Gap

`data/JP/cities.json` currently has 62 `JP-13` records, but 58 records are missing `city_name_ja`. The existing JP City tests pass, so new completeness verification is required before the City baseline can unblock Attraction/Festival spec work.
