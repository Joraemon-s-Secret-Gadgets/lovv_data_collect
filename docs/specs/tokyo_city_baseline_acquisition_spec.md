# Spec: Tokyo City Baseline Acquisition

> Source review: `docs/reports/japan_attraction_festival_spec_review.md`
> Supersedes for this phase: Attraction/Festival spec work must wait until this City baseline is complete.
> Status: Draft for user review
> Created: 2026-06-22
> Owner role: Spec Agent

## Summary

This spec defines the prerequisite Tokyo City baseline work that must be completed before any Tokyo Attraction/Festival acquisition spec is approved or decomposed for implementation.

The baseline target is all 62 Tokyo municipalities: 23 special wards plus 39 non-ward cities, towns, villages, and island municipalities. The current target files already represent the correct 62-entry scope, and `data/JP/cities.json` already has 62 `JP-13` records, but 58 records are missing `city_name_ja`. That means the current City output is not complete enough to serve as the canonical key set for Attraction/Festival mapping.

## Objective

Build a verified Tokyo City key set that downstream Attraction/Festival data can safely reference by `city_id`.

Success means every Tokyo City record has complete multilingual names, stable ID, prefecture reference, coordinates, source metadata, and field status, and rerunning the acquisition does not delete valid existing records.

## Assumptions

- The first approved scope remains Tokyo only (`JP-13`), not all Kanto prefectures.
- Target count is exactly 62 Tokyo municipalities.
- The target split is 23 special wards and 39 other municipalities.
- `crawling/JP/targets/tokyo_municipalities_ko.json` is the primary input for Korean-first acquisition.
- `crawling/JP/targets/tokyo_municipalities_ja.json` is an alignment/reference input and must remain count-aligned with the Korean target list.
- Attraction/Festival specs are blocked until this City baseline is verified.

## Goals

- Keep the Tokyo target list aligned at 62 municipalities.
- Fill `city_name_ja` from KO Wikipedia langlinks whenever available.
- Preserve `city_name_en` from langlinks without forcing an English page fetch.
- Keep `city_id` stable and based on English romanization when available.
- Preserve current City record schema while improving completeness.
- Fill the Tokyo Prefecture record from the Korean Wikipedia `도쿄도` page.
- Add Tokyo Prefecture geography and climate/weather information to `prefectures.json`.
- Fill missing lower-municipality climate/weather fields from the Tokyo Prefecture climate table in the Korean Wikipedia `도쿄도` page.
- Add rerun-safe merge behavior for `data/JP/cities.json` and `data/JP/prefectures.json`.
- Add output completeness validation so missing Japanese names are caught by tests or verification.
- Produce a verified `data/JP/cities.json` baseline before returning to Attraction/Festival spec work.

## Non-Goals

- Do not implement Attraction/Festival acquisition in this phase.
- Do not expand to non-Tokyo Kanto prefectures in this phase.
- Do not introduce database migrations or final production schema changes.
- Do not collect hotels, restaurants, booking data, or user data.
- Do not scrape unofficial blogs, social media, or commercial aggregators as authoritative City sources.
- Do not change KR acquisition behavior unless it is required by a shared helper and verified separately.

## Tech Stack

- Language: Python 3.12
- Package/test runner: `uv`
- Test framework: `pytest` / `unittest`
- HTTP source: Wikipedia HTML client using `requests`
- Parser: existing `crawling/JP/wikipedia_client.py` parsing helpers
- Output: JSON files under `data/JP`

## Commands

Use project-local `uv` commands from the repository root. On this Windows setup, set a workspace-local cache before running `uv`.

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run pytest crawling\JP\tests\test_city_wikipedia_acquisition.py
```

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run python -m crawling.JP.city_wikipedia_acquisition --input crawling\JP\targets\tokyo_municipalities_ko.json --default-prefecture-id JP-13 --output-dir data\JP --fetcher html
```

```powershell
$env:UV_CACHE_DIR='.cache\uv'
@'
import json
from pathlib import Path
cities = json.loads(Path('data/JP/cities.json').read_text(encoding='utf-8'))
assert len(cities) == 62
assert {city['prefecture_id'] for city in cities} == {'JP-13'}
assert all(city.get('city_name_ja') for city in cities)
assert all(city.get('field_status', {}).get('city_name_ja') == 'collected' for city in cities)
'@ | uv run python -
```

## Project Structure

```text
crawling/JP/city_wikipedia_acquisition.py     CLI wrapper and stable import surface
crawling/JP/pipeline.py                       Target loading, page collection, output writing
crawling/JP/normalizer.py                     City/Prefecture record normalization
crawling/JP/models.py                         CityRecord and PrefectureRecord dataclasses
crawling/JP/wikipedia_client.py               HTML/API fetch and parse helpers
crawling/JP/targets/tokyo_municipalities_*.json
                                               Tokyo 62-municipality target lists
crawling/JP/tests/test_city_wikipedia_acquisition.py
                                               Unit tests for JP City acquisition
data/JP/cities.json                           Normalized Tokyo City output
data/JP/prefectures.json                      Normalized Tokyo Prefecture output
docs/reports/japan_attraction_festival_spec_review.md
                                               Review gate that blocks Attraction/Festival work
```

## Code Style

Follow the existing JP acquisition style:

```python
def city_field_status(city: CityRecord, has_korean_page: bool = True) -> dict[str, str]:
    return {
        "city_name_ko": STATUS_NEEDS_REVIEW if city.city_name_ko and not has_korean_page else _status(city.city_name_ko),
        "city_name_ja": _status(city.city_name_ja),
        "city_name_en": _status(city.city_name_en),
        "prefecture_id": _status(city.prefecture_id),
        "location": _status(city.location),
    }
```

- Keep plain dataclasses and focused helper functions.
- Prefer existing `PageTarget`, `CityRecord`, and `PrefectureRecord` structures.
- Keep JSON output deterministic and UTF-8 encoded.
- Avoid new dependencies unless the user approves them.
- Add small tests around observed failure modes before changing acquisition behavior.

## User Flow

1. Data Acquisition Agent reads this spec and `docs/specs/TASK1_SUBTASKS.md`.
2. Implementation Agent fixes the JP City collection path so KO-source targets keep JA langlink titles.
3. Implementation Agent adds merge/rerun safety for `data/JP` outputs.
4. Implementation Agent adds a completeness check for the 62 Tokyo target records.
5. Implementation Agent runs JP City tests and then performs an approved live reacquisition.
6. Review Agent verifies that `data/JP/cities.json` is a complete canonical Tokyo key set.
7. Only after approval, Spec Agent may revisit Tokyo Attraction/Festival acquisition.

## Requirements

- REQ-TOKYO-CITY-001: The target list must contain exactly 62 Tokyo municipalities.
- REQ-TOKYO-CITY-002: The target list must include 23 special wards and 39 other municipalities.
- REQ-TOKYO-CITY-003: Korean and Japanese target files must remain count-aligned and order-aligned unless a separate mapping file is introduced.
- REQ-TOKYO-CITY-004: The workflow must output exactly one City record per target municipality.
- REQ-TOKYO-CITY-005: Every City record must have `prefecture_id == "JP-13"`.
- REQ-TOKYO-CITY-006: Every City record must have non-empty `city_id`, `city_name_ko`, `city_name_ja`, and `city_name_en`.
- REQ-TOKYO-CITY-007: `city_name_ja` must be filled from KO Wikipedia langlinks when langlinks provide a Japanese title, even when KO source coordinates are already present.
- REQ-TOKYO-CITY-008: `city_name_en` may remain a title stub from langlinks; a full English page fetch is not required for this phase.
- REQ-TOKYO-CITY-009: Every City record must have numeric `latitude` and `longitude`.
- REQ-TOKYO-CITY-010: Every City record must include `source_name`, `source_url`, `collected_at`, `field_status`, and `data_confidence`.
- REQ-TOKYO-CITY-011: Every required field must have one of `collected`, `needs_review`, `missing`, or `blocked` where supported by the model.
- REQ-TOKYO-CITY-012: Re-running acquisition must merge by stable identifiers and must not delete unrelated valid City or Prefecture records.
- REQ-TOKYO-CITY-013: The workflow must fail verification if any of the 62 Tokyo records lacks `city_name_ja`.
- REQ-TOKYO-CITY-014: The workflow must still reject non-Tokyo records for this phase.
- REQ-TOKYO-CITY-015: The implementation must not perform Attraction/Festival collection or alter Attraction/Festival specs as part of this task.
- REQ-TOKYO-CITY-016: The Tokyo Prefecture record must use `https://ko.wikipedia.org/wiki/도쿄도` as its primary source URL for prefecture-level information.
- REQ-TOKYO-CITY-017: The Tokyo Prefecture record must include non-empty `description`, `geography_description`, and `climate_table` values when the `도쿄도` page exposes the relevant sections.
- REQ-TOKYO-CITY-018: Prefecture-level geography and climate/weather fields must have field status values and must not be silently omitted from `prefectures.json`.
- REQ-TOKYO-CITY-019: When a Tokyo lower-municipality City record has no city-specific climate table, the pipeline must fill its `climate_table` from the `JP-13` Prefecture climate/weather table derived from the Korean Wikipedia `도쿄도` page.
- REQ-TOKYO-CITY-020: City-specific collected climate tables must be preserved and must not be overwritten by the prefecture-level fallback.
- REQ-TOKYO-CITY-021: Inherited City climate/weather records must retain source traceability to the `도쿄도` source URL and must set `field_status.climate_table` to `collected`.

## Design

### Collection Behavior

For KO source targets, `collect_pages()` must preserve `ja` and `en` langlink titles even when KO page coordinates already exist. The current issue is that JA pages are only fetched when KO coordinates are missing; this leaves `city_name_ja` blank for records that already have KO coordinates.

The preferred fix is to use langlink title stubs for names by default:

- `ko`: source page.
- `ja`: `{"title": linked_ja_title}` when a linked title exists.
- `en`: `{"title": linked_en_title}` when a linked title exists.

Full linked-page fetches should remain limited to cases where coordinates or richer fallback content are needed.

### Normalization Behavior

`build_city_record()` may continue to read `city_name_ja` and `city_name_en` from page titles. It should not require full JA/EN page payloads just to populate names.

### Merge Behavior

Add rerun-safe output behavior before live reacquisition:

- Read existing `cities.json` and `prefectures.json` if present.
- Merge City records by `city_id`.
- If `city_id` changes because an English title becomes newly available, use a deterministic fallback matching strategy based on target title and `prefecture_id`, then preserve or report the change.
- Merge Prefecture records by `prefecture_id`.
- Do not drop valid existing records unless they are replaced by the same stable key.

If ID reconciliation is ambiguous, write the issue to review output or fail the run rather than silently deleting data.

### Completeness Validation

Add a validation helper or test utility that checks:

- record count is 62;
- all records are `JP-13`;
- all required fields exist;
- all `city_name_ja` values are non-empty;
- all `field_status.city_name_ja` values are `collected`;
- `city_id` values are unique;
- `prefectures.json` contains `JP-13` and every City references it.

### Tokyo Prefecture Enrichment

The pipeline must fetch the Korean Wikipedia `도쿄도` page once per run and use it to enrich the `JP-13` prefecture record.

The enrichment should populate:

- `description`: a short lead summary from the `도쿄도` source page.
- `geography_description`: text from the `지리` section, with markup stripped.
- `climate_table`: the climate/weather table or climate section content from the `기후` subsection.
- `latitude` and `longitude`: representative coordinates when available from the page.

If a section cannot be parsed from Wikipedia, the corresponding field must remain visible with `missing` or `needs_review` status rather than being dropped.

### Lower-Municipality Climate Fallback

After the `JP-13` Prefecture record is built, the pipeline should apply its climate/weather table to City records whose `climate_table` is still missing or marked as `수작업 필요`.

This fallback uses the Tokyo Metropolis climate/weather table as a shared baseline for lower municipalities. It must preserve any City record that already has a collected city-specific climate table, because an individual municipality page can be more precise than the prefecture-level table.

Inherited climate/weather values should include a source URL or note that makes the fallback explicit for downstream review.

## Testing Strategy

- Unit tests must cover KO-source pages with coordinates and JA/EN langlinks.
- Unit tests must prove that `city_name_ja` is populated without requiring a full JA page fetch.
- Unit tests must cover rerun merge behavior for existing and newly collected records.
- Unit tests must cover Tokyo Prefecture enrichment from the `도쿄도` source page.
- A local completeness check must validate the generated `data/JP` output.
- Live reacquisition should be run only after unit tests pass.

## Boundaries

- Always: keep work inside the repository workspace.
- Always: use workspace-local `uv` cache for validation commands.
- Always: preserve source metadata and field status.
- Always: keep Attraction/Festival work blocked until this spec is approved and implemented.
- Ask first: running live network reacquisition if credentials, network policy, or rate limits are unclear.
- Ask first: changing output schema in a way that downstream users must migrate.
- Never: commit `.env` or real secrets.
- Never: read or write files outside this workspace.
- Never: remove failing tests or weaken completeness checks to pass.
- Never: scrape unofficial tourism sites as part of this City baseline task.

## Acceptance Criteria

- AC-TOKYO-CITY-001: `crawling/JP/targets/tokyo_municipalities_ko.json` has 62 entries.
- AC-TOKYO-CITY-002: `crawling/JP/targets/tokyo_municipalities_ja.json` has 62 entries.
- AC-TOKYO-CITY-003: `data/JP/cities.json` has 62 records after reacquisition.
- AC-TOKYO-CITY-004: All 62 records have `prefecture_id == "JP-13"`.
- AC-TOKYO-CITY-005: All 62 records have non-empty `city_name_ja`.
- AC-TOKYO-CITY-006: All 62 records have non-empty `city_name_en` unless the implementation records a specific `needs_review` reason accepted by Review Agent.
- AC-TOKYO-CITY-007: All required fields have valid field status.
- AC-TOKYO-CITY-008: JP City unit tests pass.
- AC-TOKYO-CITY-009: A rerun merge test proves existing valid records are not deleted.
- AC-TOKYO-CITY-010: Review Agent approves this City baseline before any Attraction/Festival spec proceeds.
- AC-TOKYO-CITY-011: `data/JP/prefectures.json` contains `JP-13` with `source_url` pointing at the Korean Wikipedia `도쿄도` page.
- AC-TOKYO-CITY-012: `JP-13` has non-empty `description`, `geography_description`, and `climate_table` with corresponding collected or needs-review field statuses.
- AC-TOKYO-CITY-013: After live reacquisition, all 62 Tokyo City records have `field_status.climate_table == "collected"`.
- AC-TOKYO-CITY-014: City records that inherit the prefecture-level climate table include source traceability to the Korean Wikipedia `도쿄도` page.

## Verification

Required local verification:

```powershell
$env:UV_CACHE_DIR='.cache\uv'; uv run pytest crawling\JP\tests\test_city_wikipedia_acquisition.py
```

Required output verification after live acquisition:

```powershell
$env:UV_CACHE_DIR='.cache\uv'
@'
import json
from pathlib import Path
cities = json.loads(Path('data/JP/cities.json').read_text(encoding='utf-8'))
prefectures = json.loads(Path('data/JP/prefectures.json').read_text(encoding='utf-8'))
assert len(cities) == 62, len(cities)
assert {city['prefecture_id'] for city in cities} == {'JP-13'}
assert len({city['city_id'] for city in cities}) == 62
assert all(city.get('city_name_ko') for city in cities)
assert all(city.get('city_name_ja') for city in cities)
assert all(city.get('city_name_en') for city in cities)
assert all(city.get('field_status', {}).get('city_name_ja') == 'collected' for city in cities)
prefecture_ids = {prefecture['prefecture_id'] for prefecture in prefectures}
assert 'JP-13' in prefecture_ids
assert all(city['prefecture_id'] in prefecture_ids for city in cities)
tokyo = next(prefecture for prefecture in prefectures if prefecture['prefecture_id'] == 'JP-13')
assert tokyo['source_url'] == 'https://ko.wikipedia.org/wiki/%EB%8F%84%EC%BF%84%EB%8F%84'
assert tokyo.get('description')
assert tokyo.get('geography_description')
assert tokyo.get('climate_table')
assert tokyo.get('field_status', {}).get('geography_description') in {'collected', 'needs_review'}
assert tokyo.get('field_status', {}).get('climate_table') in {'collected', 'needs_review'}
assert all(city.get('field_status', {}).get('climate_table') == 'collected' for city in cities)
assert not any((city.get('climate_table') or {}).get('caption') == '수작업 필요' for city in cities)
'@ | uv run python -
```

## Risks

- Existing `city_id` values may change if `city_name_en` becomes available for records that previously fell back to a different title.
- Some Wikipedia pages may lack langlinks or expose disambiguated titles requiring normalization.
- Existing tests pass despite current output incompleteness, so a new completeness test is required.
- Live Wikipedia access can fail due to network, throttling, or page structure changes.

## Open Questions

- Should any existing `city_id` values be preserved exactly even if improved English titles would produce a different slug?
- Should output completeness validation be a standalone CLI command or a test helper only?
- Should `blocked` be added to `crawling/JP/models.py` status constants now, or deferred until Attraction/Festival work needs it?
