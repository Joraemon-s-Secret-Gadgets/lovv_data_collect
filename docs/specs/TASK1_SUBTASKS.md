# TASK1_SUBTASKS: Tokyo City Baseline Acquisition

> Source of Truth: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
> Routing Summary: `docs/specs/tokyo_city_baseline_acquisition_summary.md`
> Blocking Review: `docs/reports/japan_attraction_festival_spec_review.md`
> Base branch: `feature/japan-data-acquisition`
> Responsible role: Implementation Agent, then Review Agent

## Context And Dependencies

This Task exists because Attraction/Festival specs must not proceed until the Tokyo City baseline is complete. Current target lists already cover 62 Tokyo municipalities, but current output has 58 records missing `city_name_ja`.

Implementation must start at Subtask 1 and proceed in order. After each Subtask is implemented and locally verified, stop and report verification results before moving to the next Subtask.

## Deadlock Escape Conditions

Stop and escalate to the user after:

- three consecutive failures of the same test or verification command;
- repeated uncertainty about whether to preserve or regenerate existing `city_id` values;
- any need to access files outside this workspace;
- any live network acquisition failure that cannot be resolved by changing timeout/backoff or using fixtures;
- any review deadlock that repeats three consecutive times.

## Subtask 1: Preserve JA/EN Langlink Titles For KO Tokyo Targets

- Purpose: KO Wikipedia pages that already have coordinates must still populate `city_name_ja` and `city_name_en` from langlinks.
- Required Context:
  - The current output has 62 Tokyo records but 58 missing Japanese names.
  - `collect_pages()` currently fetches or stubs JA data only in coordinate fallback paths.
- Context Budget:
  - Must read:
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#requirements`
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#design`
    - `crawling/JP/pipeline.py`
    - `crawling/JP/normalizer.py`
    - `crawling/JP/tests/test_city_wikipedia_acquisition.py`
  - Do not read:
    - Attraction/Festival implementation files unless a test import requires them.
    - `AGENTS.ko.md`
  - Optional read:
    - `crawling/JP/wikipedia_client.py` if langlink parsing behavior is unclear.
- Source of Truth:
  - Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Required Sections:
  - `#requirements`
  - `#design`
  - `#acceptance-criteria`
- Must Read Before Implementation:
  - `#collection-behavior`
  - `#normalization-behavior`
  - `#testing-strategy`
- Target Files:
  - `crawling/JP/pipeline.py`
  - `crawling/JP/tests/test_city_wikipedia_acquisition.py`
- Out of Scope:
  - Live reacquisition.
  - Non-Tokyo Kanto expansion.
  - Attraction/Festival specs or code.
- Acceptance Criteria:
  - KO-source pages with JA/EN langlinks populate `city_name_ja` and `city_name_en` even when KO coordinates are present.
  - Existing coordinate fallback tests still pass.
  - No full JA page fetch is required only to populate the Japanese title.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run pytest crawling\JP\tests\test_city_wikipedia_acquisition.py`

## Subtask 2: Add Rerun-Safe Merge For JP City Outputs

- Purpose: Live reacquisition must not delete valid existing Tokyo City or Prefecture records.
- Required Context:
  - Existing `acquire_city_data()` writes `prefectures.json` and `cities.json` directly.
  - The new baseline must be safe to rerun before Attraction/Festival work depends on it.
- Context Budget:
  - Must read:
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#merge-behavior`
    - `crawling/JP/pipeline.py`
    - `crawling/JP/models.py`
    - `crawling/JP/tests/test_city_wikipedia_acquisition.py`
  - Do not read:
    - KR pipeline files unless needed only to mirror a known merge pattern.
  - Optional read:
    - `crawling/KR/pipeline.py` if a local merge helper pattern is needed.
- Source of Truth:
  - Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Required Sections:
  - `#merge-behavior`
  - `#acceptance-criteria`
- Must Read Before Implementation:
  - `#merge-behavior`
  - `#verification`
- Target Files:
  - `crawling/JP/pipeline.py`
  - `crawling/JP/tests/test_city_wikipedia_acquisition.py`
- Out of Scope:
  - Changing City JSON schema unless required for merge metadata and approved.
  - Deleting existing data files.
- Acceptance Criteria:
  - Existing output is read before writing when files exist.
  - City records merge by stable key with deterministic conflict behavior.
  - Prefecture records merge by `prefecture_id`.
  - A unit test proves rerun merge does not remove unrelated valid records.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run pytest crawling\JP\tests\test_city_wikipedia_acquisition.py`

## Subtask 2A: Add Tokyo Prefecture Geography And Weather Enrichment

- Purpose: `data/JP/prefectures.json` must hold Tokyo Metropolis information from the Korean Wikipedia `도쿄도` page before downstream Attraction/Festival mapping uses `JP-13`.
- Required Context:
  - User requested the `https://ko.wikipedia.org/wiki/도쿄도` page as the source for Tokyo prefecture information.
  - City records already carry geography and climate/weather fields, but Prefecture records currently do not.
- Context Budget:
  - Must read:
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#tokyo-prefecture-enrichment`
    - `crawling/JP/models.py`
    - `crawling/JP/pipeline.py`
    - `crawling/JP/wikipedia_client.py`
  - Do not read:
    - `AGENTS.ko.md`
    - Attraction/Festival implementation files.
  - Optional read:
    - `crawling/JP/normalizer.py` only for reuse of existing section extraction behavior.
- Source of Truth:
  - Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Required Sections:
  - `#tokyo-prefecture-enrichment`
  - `#acceptance-criteria`
- Must Read Before Implementation:
  - `#tokyo-prefecture-enrichment`
  - `#verification`
- Target Files:
  - `crawling/JP/models.py`
  - `crawling/JP/pipeline.py`
  - `crawling/JP/wikipedia_client.py`
  - `crawling/JP/tests/`
- Out of Scope:
  - Non-Tokyo prefecture enrichment.
  - Attraction/Festival collection.
- Acceptance Criteria:
  - The pipeline fetches the Korean Wikipedia `도쿄도` page for `JP-13`.
  - `prefectures.json` includes `description`, `geography_description`, `climate_table`, and field statuses for those fields.
  - HTML langlink parsing no longer promotes category or Japanese-script anchors into `city_name_en`.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run pytest crawling\JP\tests`

## Subtask 2B: Fill Lower-Municipality Weather From Tokyo Prefecture Table

- Purpose: City records whose own Wikipedia page has no climate/weather table must inherit the Tokyo Prefecture climate/weather table derived from the Korean Wikipedia `도쿄도` page.
- Required Context:
  - The user requested lower-municipality weather to be filled from the weather table in the `도쿄도` source page.
  - The current live output still has many City records with `climate_table.caption == "수작업 필요"`.
  - City-specific collected climate/weather tables must remain more authoritative than the prefecture fallback.
- Context Budget:
  - Must read:
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#lower-municipality-climate-fallback`
    - `crawling/JP/pipeline.py`
    - `crawling/JP/models.py`
    - `crawling/JP/prefecture_enrichment.py`
  - Do not read:
    - `AGENTS.ko.md`
    - Attraction/Festival implementation files.
    - Unrelated KR vector index files.
- Source of Truth:
  - Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Required Sections:
  - `#lower-municipality-climate-fallback`
  - `#acceptance-criteria`
  - `#verification`
- Target Files:
  - `crawling/JP/pipeline.py`
  - `crawling/JP/tests/`
  - Optional: a focused JP climate inheritance helper module.
- Out of Scope:
  - Per-municipality climate station matching.
  - Replacing city-specific collected climate/weather tables.
  - Attraction/Festival collection.
- Acceptance Criteria:
  - City records missing climate/weather data inherit a collected climate table from `JP-13`.
  - Inherited values keep source traceability to the Korean Wikipedia `도쿄도` page.
  - City records with an already collected city-specific climate/weather table are preserved.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run pytest crawling\JP\tests`

## Subtask 3: Add Tokyo Baseline Completeness Verification

- Purpose: The current tests pass despite `city_name_ja` being missing in most output records; this gap must be caught automatically.
- Required Context:
  - The baseline gate requires exactly 62 Tokyo records and non-empty required fields.
- Context Budget:
  - Must read:
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#completeness-validation`
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#acceptance-criteria`
    - `crawling/JP/tests/test_city_wikipedia_acquisition.py`
  - Do not read:
    - Large data files beyond targeted JSON inspection.
  - Optional read:
    - `data/JP/cities.json` and `data/JP/prefectures.json` through targeted validation only.
- Source of Truth:
  - Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Required Sections:
  - `#completeness-validation`
  - `#verification`
- Must Read Before Implementation:
  - `#completeness-validation`
  - `#acceptance-criteria`
- Target Files:
  - `crawling/JP/tests/test_city_wikipedia_acquisition.py`
  - Optional: `crawling/JP/pipeline.py` or a focused validation helper if tests need shared logic.
- Out of Scope:
  - Live reacquisition.
  - Modifying Attraction/Festival specs.
- Acceptance Criteria:
  - Verification fails if any of the 62 Tokyo records lacks `city_name_ja`.
  - Verification checks record count, unique `city_id`, `JP-13` prefecture, and valid prefecture references.
  - The check is documented in the test or helper name.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run pytest crawling\JP\tests\test_city_wikipedia_acquisition.py`

## Subtask 4: Run Approved Tokyo City Reacquisition And Verify Output

- Purpose: Regenerate `data/JP/cities.json` and `data/JP/prefectures.json` after the code path is fixed.
- Required Context:
  - Live reacquisition touches public Wikipedia pages and writes tracked `data/JP` JSON outputs.
- Context Budget:
  - Must read:
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#commands`
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#verification`
    - `crawling/JP/city_wikipedia_acquisition.py`
  - Do not read:
    - `.env` files.
    - Large logs or unrelated data artifacts.
  - Optional read:
    - `data/JP/cities.json` and `data/JP/prefectures.json` after regeneration.
- Source of Truth:
  - Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Required Sections:
  - `#commands`
  - `#verification`
- Must Read Before Implementation:
  - `#commands`
  - `#boundaries`
  - `#verification`
- Target Files:
  - `data/JP/cities.json`
  - `data/JP/prefectures.json`
- Out of Scope:
  - Code changes beyond fixes already completed in prior Subtasks.
  - Non-Tokyo data collection.
- Acceptance Criteria:
  - `data/JP/cities.json` has exactly 62 records.
  - All records are `JP-13`.
  - All records have non-empty `city_name_ja`.
  - All records have `field_status.climate_table == "collected"`.
  - No record keeps `climate_table.caption == "수작업 필요"`.
  - The verification snippet in the Full Spec passes.
- Verification:
  - `$env:UV_CACHE_DIR='.cache\uv'; uv run python -m crawling.JP.city_wikipedia_acquisition --input crawling\JP\targets\tokyo_municipalities_ko.json --default-prefecture-id JP-13 --output-dir data\JP --fetcher html`
  - Run the output verification snippet from `docs/specs/tokyo_city_baseline_acquisition_spec.md#verification`.

## Subtask 5: Review Gate For Attraction/Festival Unblock

- Purpose: Confirm that the City baseline is complete before returning to Attraction/Festival specs.
- Required Context:
  - The review report explicitly blocks Attraction/Festival spec work until this baseline passes.
- Context Budget:
  - Must read:
    - `docs/reports/japan_attraction_festival_spec_review.md`
    - `docs/specs/tokyo_city_baseline_acquisition_spec.md#acceptance-criteria`
    - Changed files from Subtasks 1-4
  - Do not read:
    - Unrelated KR vector index files.
  - Optional read:
    - Generated `data/JP` JSON files through targeted checks.
- Source of Truth:
  - Full Spec: `docs/specs/tokyo_city_baseline_acquisition_spec.md`
- Required Sections:
  - `#acceptance-criteria`
  - `#verification`
- Must Read Before Implementation:
  - `#acceptance-criteria`
  - `#verification`
- Target Files:
  - `docs/reports/TASK1_COMPLETION.md`
- Out of Scope:
  - Starting Attraction/Festival implementation.
- Acceptance Criteria:
  - Review Agent reports no Blocker findings for the City baseline.
  - `docs/reports/TASK1_COMPLETION.md` summarizes changed files, verification, and remaining risks.
  - If Attraction/Festival work is still blocked, the report says why.
- Verification:
  - Re-run JP City tests.
  - Re-run output completeness verification.
  - Manually compare results against this Task sheet.
