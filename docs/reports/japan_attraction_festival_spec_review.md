# Japan Attraction/Festival Spec Review

> Review timestamp: 2026-06-22 14:51:58 +0900
> Responsible agent: Review Agent
> Branch: `feature/japan-data-acquisition`
> Scope:
> - `docs/specs/tokyo_attraction_festival_acquisition_spec.md`
> - `docs/specs/kanto_attraction_festival_acquisition_spec.md`
> - Related context: `docs/japan_data_acquisition_plan.md`, source/license reports, current `crawling/JP` implementation, `data/JP` outputs

## Verdict

Not approved for implementation as-is.

User direction on 2026-06-22: do not continue Attraction/Festival spec creation before completing Tokyo City acquisition first.

The immediate prerequisite is a verified Tokyo City baseline covering all 62 Tokyo municipalities: 23 special wards plus 39 non-ward cities, towns, villages, and island municipalities. The current target files already list 62 Tokyo municipalities, and `data/JP/cities.json` also has 62 `JP-13` records, but 58 records are missing `city_name_ja`. Therefore the City baseline is not complete enough to serve as the canonical key set for Attraction/Festival mapping.

The Tokyo-first Attraction/Festival direction is reasonable only after that City baseline is fixed and verified. The Kanto expansion spec has an additional blocking dependency: non-Tokyo City data is not available and the current JP pipeline rejects non-Tokyo cities. Phase 2 should wait until the City expansion decision is made and captured as a prerequisite task.

## City Baseline Gate

Before any Attraction/Festival spec is approved or decomposed into implementation tasks:

- `crawling/JP/targets/tokyo_municipalities_ko.json` and `crawling/JP/targets/tokyo_municipalities_ja.json` must remain aligned at 62 Tokyo municipalities.
- `data/JP/cities.json` must contain 62 Tokyo City records: 23 wards and 39 other municipalities.
- Every City record must include `city_id`, `city_name_ko`, `city_name_ja`, `city_name_en`, `prefecture_id`, coordinates, source metadata, and `field_status`.
- The JP City pipeline must not leave Japanese names blank when KO Wikipedia langlinks provide them.
- Re-running the City acquisition must not delete existing valid Tokyo records.
- Only after the above is verified should the Attraction/Festival spec be rewritten or approved against those City IDs.

Current baseline check:

- `data/JP/cities.json` contains 62 records and all sampled records are `JP-13`.
- The current target files represent Tokyo's 62 municipalities: 23 special wards plus 39 other municipalities.
- 58 of the 62 current City records are missing `city_name_ja`, so the baseline is incomplete.
- `uv run pytest crawling\JP\tests\test_city_wikipedia_acquisition.py` passes 19 tests, but this test set does not currently fail on the existing output completeness gap.
- Immediate live reacquisition should wait until the JP City pipeline fixes Japanese-name extraction and rerun-safe merge behavior; otherwise the command can overwrite outputs while preserving the same completeness problem.

## Findings

- Severity: Blocker
- Area: Spec Alignment
- Evidence: `docs/specs/kanto_attraction_festival_acquisition_spec.md:37` requires every record to connect to existing City `city_id`, while `docs/specs/kanto_attraction_festival_acquisition_spec.md:44` keeps City collection out of scope. The same spec later requires Phase 2 output for Chiba, Saitama, and Tochigi at `docs/specs/kanto_attraction_festival_acquisition_spec.md:114-115`, but also admits at `docs/specs/kanto_attraction_festival_acquisition_spec.md:133` that Kanto 6-prefecture City data has not been collected. Current code enforces Tokyo only in `crawling/JP/pipeline.py:21` and `crawling/JP/pipeline.py:81-84`; local inspection shows `data/JP/cities.json` has 62 records and the first/last sampled records are both `JP-13`.
- Risk: Phase 2 cannot satisfy `city_id` acceptance criteria. If implementation starts from dataeye/BODIK adapters first, it will either create unmapped Attraction/Festival records or weaken the requirement that every destination entity belongs to a valid City.
- Required Fix: Split the approved path into Phase 1 Tokyo-only work, then add a prerequisite City expansion task before any Phase 2 adapter task. That task must generalize the Tokyo hard lock, collect JP-08/09/10/11/12/14 City records, and verify those cities exist before Attraction/Festival mapping starts. Alternatively, keep Phase 2 explicitly unapproved until the user chooses the sequencing noted in `docs/specs/kanto_attraction_festival_acquisition_spec.md:199-201`.
- Retest: Before approving Phase 2, verify `data/JP/cities.json` contains valid City records for the target Kanto prefectures and run a mapping test that joins sample Chiba/Saitama/Tochigi POI records to those city IDs.

- Severity: Major
- Area: Correctness
- Evidence: Tokyo spec requires existing-output merge by "City pipeline merge" at `docs/specs/tokyo_attraction_festival_acquisition_spec.md:146`, and Kanto spec repeats `data/JP merge` at `docs/specs/kanto_attraction_festival_acquisition_spec.md:56` and `docs/specs/kanto_attraction_festival_acquisition_spec.md:90`. Current JP city pipeline writes `prefectures.json` and `cities.json` directly in `crawling/JP/pipeline.py:95-98`; the license investigation report also states JP lacks KR-style merge and overwrites files at `docs/reports/japan_data_source_license_investigation_report.md:21-23`.
- Risk: Implementers may assume reusable merge behavior exists and accidentally overwrite generated data on reruns. This is especially risky once Attraction/Festival outputs, license metadata, review queues, and Wikidata/OSM enrichments are added.
- Required Fix: Define concrete output files and merge keys before implementation, for example `data/JP/attractions.json`, `data/JP/festivals.json`, and review/quarantine manifests. Specify stable ID generation, duplicate thresholds, conflict resolution, and whether unmatched records are excluded from primary output or written to a separate `needs_review` file.
- Retest: Add rerun tests that start from existing output, ingest one new fixture plus one duplicate fixture, and prove the duplicate is updated/merged without deleting unrelated records.

- Severity: Major
- Area: Security
- Evidence: Kanto spec introduces Wikidata/OSM fallback at `docs/specs/kanto_attraction_festival_acquisition_spec.md:40`, `docs/specs/kanto_attraction_festival_acquisition_spec.md:108`, `docs/specs/kanto_attraction_festival_acquisition_spec.md:119`, and `docs/specs/kanto_attraction_festival_acquisition_spec.md:179`, but the common metadata only requires `license` and `commercial_use_allowed` through the Tokyo spec fields at `docs/specs/tokyo_attraction_festival_acquisition_spec.md:131-135`. The portal directory identifies OSM as ODbL with ShareAlike isolation needs at `docs/reports/japan_tourism_opendata_portal_directory.md:127-128`, and the license report calls for source registry fields such as `requires_consent` and `redistribution_allowed` at `docs/reports/japan_data_source_license_investigation_report.md:130`.
- Risk: `commercial_use_allowed=true/false` is too coarse for ODbL, CC-BY-SA, consent-required, and redistribution-restricted sources. OSM-derived records could be mixed into product data without the database-share obligations being tracked, making later commercial filtering unreliable.
- Required Fix: Either remove OSM from the approved implementation scope and keep Wikidata-only fallback for this phase, or extend the source registry and record metadata with `requires_consent`, `redistribution_allowed`, `sharealike_required`, `license_mode`, and isolation policy. The spec should also define how these fields affect export, product use, and review queues.
- Retest: Add license gate tests for CC0, CC-BY, NC, consent-required, and ODbL/ShareAlike cases, including a commercial-mode export test that excludes or isolates restricted records.

- Severity: Major
- Area: External API
- Evidence: Tokyo collection relies on CKAN `package_search` and CSV downloads at `docs/specs/tokyo_attraction_festival_acquisition_spec.md:79-83`. Kanto extends this to `discover()`, `fetch_csv()`, and `license_of()` adapters at `docs/specs/kanto_attraction_festival_acquisition_spec.md:102-108`. Neither spec defines timeout, retry limit, pagination handling, max response size, rate limiting, user agent, HTTP error contract, or offline fixture boundaries.
- Risk: A crawler can hang, repeatedly hit public portals, silently skip paginated resources, or make unit tests depend on live external services. That makes the pipeline brittle and can violate polite-access expectations for public data portals.
- Required Fix: Add an external API contract to the spec: default timeout, retry/backoff cap, pagination strategy, max CSV size or row limit for test runs, user-agent string, error/status model, and a rule that unit tests use fixtures while live probes are explicit integration checks.
- Retest: Add adapter tests for timeout, non-200 response, malformed JSON, missing CSV resource, pagination, oversized CSV, and encoding fallback.

- Severity: Major
- Area: Security
- Evidence: Both specs forbid copying long external prose (`docs/specs/tokyo_attraction_festival_acquisition_spec.md:40`, `docs/specs/kanto_attraction_festival_acquisition_spec.md:48`) while making `description` a required output generated from source `説明` (`docs/specs/tokyo_attraction_festival_acquisition_spec.md:102` and `docs/specs/tokyo_attraction_festival_acquisition_spec.md:122`). The license report explains that creative descriptions are copyright-sensitive and should be internally summarized at `docs/reports/japan_data_source_license_investigation_report.md:62`.
- Risk: Without a concrete transformation rule, implementers may store copied source descriptions as service copy, or tests may approve a field merely because text exists. That weakens the stated copyright boundary.
- Required Fix: Define how descriptions are produced: allowed source text handling, max length, language, summary/rewrite method, provenance, and fallback behavior. If no safe summarization path exists in the current task, set `description` to `needs_review` instead of requiring a collected value.
- Retest: Add fixture tests that reject verbatim long descriptions and verify copied source text is either summarized under the rule or marked `needs_review`.

- Severity: Minor
- Area: Maintainability
- Evidence: Current Task Breakdown entries in `docs/specs/tokyo_attraction_festival_acquisition_spec.md:175-217` and `docs/specs/kanto_attraction_festival_acquisition_spec.md:140-189` are useful feature tasks, but they do not yet include implementation-ready context packets such as `Target Files`, `Out of Scope`, `Must Read Before Implementation`, and per-subtask verification commands. The Kanto spec notes that Task Agent decomposition happens after approval at `docs/specs/kanto_attraction_festival_acquisition_spec.md:202`.
- Risk: If these high-level tasks are handed directly to an Implementation Agent, the agent may read too much context, touch the wrong modules, or mix adapter, normalization, mapping, and license work in one oversized change.
- Required Fix: Before implementation, run Task Agent decomposition and create atomic subtasks following `docs/agents/context-loading.md` and `docs/agents/spec-task-format.md`.
- Retest: Review the generated subtask sheet for one source of truth, target files, out-of-scope items, acceptance criteria, and verification commands per subtask.

## Security Checklist Summary

- Secrets: No hardcoded secrets found in the reviewed specs.
- Workspace Safety: Specs refer to workspace-local paths only; no required outside-workspace writes were found.
- External API: Not approved until timeout/retry/pagination/error contracts are added.
- License/Data Rights: Not approved until OSM/ODbL and copied-description handling are made explicit.

## Recommended Approval Path

1. Stop Attraction/Festival spec work until Tokyo City baseline acquisition is fixed and verified for 23 wards plus 39 other Tokyo municipalities.
2. Fix the JP City acquisition gaps first: langlinks-based `city_name_ja`, stable merge/rerun behavior, and output completeness checks.
3. After Tokyo City baseline verification, rewrite/approve the Tokyo Attraction/Festival spec against the verified City IDs.
4. Hold Kanto Phase 2 until the user decides whether Kanto City expansion runs before or alongside Attraction/Festival work.
5. If Phase 2 is kept, add a City expansion prerequisite task and make adapter tasks depend on verified non-Tokyo `city_id` coverage.
6. Keep OSM out of implementation scope unless the source registry and export isolation rules are expanded first.
