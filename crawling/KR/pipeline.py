"""
Wikipedia-first city acquisition pipeline orchestration for South Korea.

This file coordinates page fetches from Korean Wikipedia, normalization,
target loading, and JSON output writing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawling.JP.pipeline import PageTarget, write_json
from crawling.KR.wikipedia_client import WikipediaClient, WikipediaHtmlClient
from crawling.JP.wikipedia_client import first_page
from crawling.KR.models import CityRecord, PrefectureRecord
from crawling.KR.normalizer import build_city_record, build_prefecture_record
from crawling.KR.provinces import find_province

logger = logging.getLogger(__name__)


@dataclass
class ProvinceResult:
    """Tracks progress and outcome of a single province acquisition run."""

    province_id: str
    newly_acquired: int = 0
    skipped: int = 0
    failed: int = 0
    failed_titles: list[str] | None = None

    def __post_init__(self) -> None:
        if self.failed_titles is None:
            self.failed_titles = []


def load_targets(
    path: Path | None,
    titles: list[str],
    default_lang: str = "ko",
    default_prefecture_id: str = "",
) -> list[PageTarget]:
    if path is None:
        return [PageTarget(title=title, lang=default_lang, prefecture_id=default_prefecture_id) for title in titles]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Input file must be a JSON array of city page titles or target objects.")
    targets: list[PageTarget] = []
    for item in payload:
        if isinstance(item, str):
            targets.append(PageTarget(title=item, lang=default_lang, prefecture_id=default_prefecture_id))
        elif isinstance(item, dict) and isinstance(item.get("title"), str):
            targets.append(
                PageTarget(
                    title=item["title"],
                    lang=str(item.get("lang") or default_lang),
                    prefecture_id=str(item.get("prefecture_id") or default_prefecture_id),
                )
            )
        else:
            raise ValueError("Input file must contain strings or objects with a title field.")
    return targets


def acquire_city_data(
    titles: list[str] | list[PageTarget],
    output_dir: Path,
    client: WikipediaClient | None = None,
    source_lang: str = "ko",
) -> tuple[list[PrefectureRecord], list[CityRecord]]:
    wikipedia = client or WikipediaHtmlClient()
    collected_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    
    # Load existing cities to avoid overwriting previous run outputs
    existing_cities: dict[str, CityRecord] = {}
    cities_path = output_dir / "cities.json"
    if cities_path.exists():
        try:
            raw_list = json.loads(cities_path.read_text(encoding="utf-8"))
            for item in raw_list:
                city = CityRecord(
                    city_id=item.get("city_id", ""),
                    city_name_ko=item.get("city_name_ko", ""),
                    city_name_ja=item.get("city_name_ja", ""),
                    city_name_en=item.get("city_name_en", ""),
                    prefecture_id=item.get("prefecture_id", ""),
                    location=item.get("location", ""),
                    latitude=item.get("latitude"),
                    longitude=item.get("longitude"),
                    description=item.get("description", ""),
                    geography_description=item.get("geography_description", ""),
                    climate_table=item.get("climate_table"),
                    site_urls=item.get("site_urls", []),
                    source_name=item.get("source_name", ""),
                    source_url=item.get("source_url", ""),
                    collected_at=item.get("collected_at", ""),
                    field_status=item.get("field_status", {}),
                    data_confidence=item.get("data_confidence", "medium"),
                    verified_at=item.get("verified_at"),
                    verified_source_url=item.get("verified_source_url"),
                    verification_note=item.get("verification_note"),
                )
                existing_cities[city.city_id] = city
        except Exception as e:
            print(f"Warning: Could not load existing cities for merging: {e}")

    # Load existing prefectures (provinces)
    existing_prefectures: dict[str, PrefectureRecord] = {}
    prefectures_path = output_dir / "prefectures.json"
    if prefectures_path.exists():
        try:
            raw_list = json.loads(prefectures_path.read_text(encoding="utf-8"))
            for item in raw_list:
                pref = PrefectureRecord(
                    prefecture_id=item.get("prefecture_id", ""),
                    name_ko=item.get("name_ko", ""),
                    name_ja=item.get("name_ja", ""),
                    name_en=item.get("name_en", ""),
                    region=item.get("region", ""),
                    source_name=item.get("source_name", ""),
                    source_url=item.get("source_url", ""),
                    collected_at=item.get("collected_at", ""),
                    field_status=item.get("field_status", {}),
                    data_confidence=item.get("data_confidence", "medium"),
                    verified_at=item.get("verified_at"),
                    verified_source_url=item.get("verified_source_url"),
                    verification_note=item.get("verification_note"),
                )
                existing_prefectures[pref.prefecture_id] = pref
        except Exception as e:
            print(f"Warning: Could not load existing prefectures for merging: {e}")

    targets = _coerce_targets(titles, source_lang)
    prefetched_pages = _prefetch_source_pages(wikipedia, targets)

    for target in targets:
        source_page = prefetched_pages.get((target.lang, target.title)) or first_page(
            wikipedia.fetch_page(target.lang, target.title)
        )
        
        pages = {
            "source": source_page,
            "ko": source_page,
            "ja": {},
            "en": {},
            "source_meta": {"lang": target.lang, "title": target.title},
        }
        
        city = build_city_record(pages, collected_at, fallback_prefecture_id=target.prefecture_id)
        existing_cities[city.city_id] = city

        province = find_province(city.prefecture_id)
        if province is not None:
            existing_prefectures[province.prefecture_id] = build_prefecture_record(
                province=province,
                collected_at=collected_at,
                source_url=city.source_url,
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    prefecture_records = sorted(existing_prefectures.values(), key=lambda item: item.prefecture_id)
    city_records = sorted(existing_cities.values(), key=lambda item: item.city_id)
    
    write_json(output_dir / "prefectures.json", prefecture_records)
    write_json(output_dir / "cities.json", city_records)
    return prefecture_records, city_records


def _coerce_targets(titles: list[str] | list[PageTarget], source_lang: str) -> list[PageTarget]:
    if not titles:
        return []
    first = titles[0]
    if isinstance(first, PageTarget):
        return titles  # type: ignore[return-value]
    return [PageTarget(title=str(title), lang=source_lang) for title in titles]


def _prefetch_source_pages(client: WikipediaClient, targets: list[PageTarget]) -> dict[tuple[str, str], dict]:
    fetch_pages = getattr(client, "fetch_pages", None)
    if fetch_pages is None:
        return {}
    pages: dict[tuple[str, str], dict] = {}
    targets_by_lang: dict[str, list[PageTarget]] = {}
    for target in targets:
        targets_by_lang.setdefault(target.lang, []).append(target)
    for lang, lang_targets in targets_by_lang.items():
        title_payloads = fetch_pages(lang, [target.title for target in lang_targets])
        for target in lang_targets:
            payload = title_payloads.get(target.title)
            if payload:
                pages[(target.lang, target.title)] = first_page(payload)
    return pages


# ────────────────────────────────────────────────────────────────────────────
# Province-aware batch execution (Task 2.1 / 2.2)
# ────────────────────────────────────────────────────────────────────────────

# Import here to avoid circular import at module level; the map is defined
# in city_wikipedia_acquisition.py but also needs to be accessible from
# pipeline without importing the CLI module.
_PROVINCE_TARGET_MAP: dict[str, str] = {
    "KR-11": "seoul_municipalities_ko.json",
    "KR-26": "busan_municipalities_ko.json",
    "KR-27": "daegu_municipalities_ko.json",
    "KR-28": "incheon_municipalities_ko.json",
    "KR-29": "gwangju_municipalities_ko.json",
    "KR-30": "daejeon_municipalities_ko.json",
    "KR-31": "ulsan_municipalities_ko.json",
    "KR-36": "sejong_municipalities_ko.json",
    "KR-41": "gyeonggi_municipalities_ko.json",
    "KR-42": "gangwon_municipalities_ko.json",
    "KR-43": "chungbuk_municipalities_ko.json",
    "KR-44": "chungnam_municipalities_ko.json",
    "KR-45": "jeonbuk_municipalities_ko.json",
    "KR-46": "jeonnam_municipalities_ko.json",
    "KR-47": "gyeongbuk_municipalities_ko.json",
    "KR-48": "gyeongnam_municipalities_ko.json",
    "KR-50": "jeju_municipalities_ko.json",
}


def acquire_province(
    province_id: str,
    output_dir: Path,
    client: WikipediaClient | None = None,
    targets_dir: Path | None = None,
) -> ProvinceResult:
    """Acquire city data for a single province.

    Resolves the target file for *province_id*, loads its municipality
    titles, and calls ``acquire_city_data`` with the correct
    ``default_prefecture_id``.  Failures on individual municipalities are
    caught and recorded; successfully collected records are always persisted.

    Returns a :class:`ProvinceResult` summarizing the outcome.
    """
    if province_id not in _PROVINCE_TARGET_MAP:
        raise ValueError(
            f"Unknown province_id '{province_id}'. "
            f"Valid: {', '.join(sorted(_PROVINCE_TARGET_MAP.keys()))}"
        )

    targets_dir = targets_dir or Path(__file__).parent / "targets"
    target_file = targets_dir / _PROVINCE_TARGET_MAP[province_id]
    wikipedia = client or WikipediaHtmlClient()

    # Load targets for this province
    targets = load_targets(
        path=target_file,
        titles=[],
        default_lang="ko",
        default_prefecture_id=province_id,
    )

    # Determine which cities already exist to compute skip count
    cities_path = output_dir / "cities.json"
    existing_ids: set[str] = set()
    if cities_path.exists():
        try:
            raw_list = json.loads(cities_path.read_text(encoding="utf-8"))
            existing_ids = {item.get("city_id", "") for item in raw_list}
        except Exception:
            pass

    result = ProvinceResult(province_id=province_id)
    successful_targets: list[PageTarget] = []

    for target in targets:
        try:
            # Quick skip check based on expected city_id pattern
            from crawling.KR.provinces import MUNICIPALITY_EN_MAP

            en_name = MUNICIPALITY_EN_MAP.get(target.title, "")
            expected_id = f"{province_id}-{en_name}" if en_name else ""
            if expected_id and expected_id in existing_ids:
                result.skipped += 1
                continue
            successful_targets.append(target)
        except Exception as e:
            logger.warning("Failed pre-check for '%s': %s", target.title, e)
            successful_targets.append(target)

    # Process the non-skipped targets with failure isolation
    failed_titles: list[str] = []
    targets_to_process: list[PageTarget] = []

    for target in successful_targets:
        targets_to_process.append(target)

    if targets_to_process:
        try:
            acquire_city_data(
                titles=targets_to_process,
                output_dir=output_dir,
                client=wikipedia,
                source_lang="ko",
            )
            result.newly_acquired = len(targets_to_process)
        except Exception as e:
            # On batch failure, try one-by-one for failure isolation
            logger.warning(
                "Batch acquisition failed for province %s, retrying individually: %s",
                province_id,
                e,
            )
            for target in targets_to_process:
                try:
                    acquire_city_data(
                        titles=[target],
                        output_dir=output_dir,
                        client=wikipedia,
                        source_lang="ko",
                    )
                    result.newly_acquired += 1
                except Exception as individual_error:
                    logger.error(
                        "Failed to acquire '%s' in province %s: %s",
                        target.title,
                        province_id,
                        individual_error,
                    )
                    result.failed += 1
                    failed_titles.append(target.title)

    result.failed_titles = failed_titles
    logger.info(
        "Province %s: %d new, %d skipped, %d failed",
        province_id,
        result.newly_acquired,
        result.skipped,
        result.failed,
    )
    return result


def acquire_all_provinces(
    output_dir: Path,
    client: WikipediaClient | None = None,
    targets_dir: Path | None = None,
) -> list[ProvinceResult]:
    """Acquire city data for all 17 Korean provinces sequentially.

    Each province's results are incrementally merged into the existing
    ``cities.json``, so partial failures do not discard other provinces'
    data.

    Returns a list of :class:`ProvinceResult` objects, one per province.
    """
    results: list[ProvinceResult] = []
    total_provinces = len(_PROVINCE_TARGET_MAP)

    for idx, province_id in enumerate(sorted(_PROVINCE_TARGET_MAP.keys()), start=1):
        logger.info(
            "Processing province %d/%d: %s", idx, total_provinces, province_id
        )
        try:
            result = acquire_province(
                province_id=province_id,
                output_dir=output_dir,
                client=client,
                targets_dir=targets_dir,
            )
            results.append(result)
        except Exception as e:
            logger.error("Province %s failed entirely: %s", province_id, e)
            results.append(
                ProvinceResult(province_id=province_id, failed=1, failed_titles=[str(e)])
            )

    # Summary log
    total_new = sum(r.newly_acquired for r in results)
    total_skipped = sum(r.skipped for r in results)
    total_failed = sum(r.failed for r in results)
    logger.info(
        "All provinces done: %d new, %d skipped, %d failed across %d provinces",
        total_new,
        total_skipped,
        total_failed,
        total_provinces,
    )
    return results
