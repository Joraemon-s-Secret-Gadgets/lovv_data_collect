"""
Wikipedia-first city acquisition pipeline orchestration for South Korea.

This file coordinates page fetches from Korean Wikipedia, normalization,
target loading, and JSON output writing.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawling.JP.pipeline import PageTarget, write_json
from crawling.KR.wikipedia_client import WikipediaClient, WikipediaHtmlClient
from crawling.JP.wikipedia_client import first_page
from crawling.KR.models import CityRecord, PrefectureRecord
from crawling.KR.normalizer import build_city_record, build_prefecture_record
from crawling.KR.provinces import find_province


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
