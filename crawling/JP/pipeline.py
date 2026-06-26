"""
Wikipedia 우선 도시 취득 파이프라인 조율.

이 파일은 페이지 가져오기, 정규화, 대상 로딩, JSON 출력 쓰기를 조율한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from crawling.JP.climate_inheritance import fill_missing_city_climate_tables
from crawling.JP.models import CityRecord, NormalizedRecord, PrefectureRecord
from crawling.JP.normalizer import build_city_record
from crawling.JP.prefecture_enrichment import build_prefecture_record_for_city
from crawling.JP.prefectures import find_prefecture
from crawling.JP.title_filters import is_valid_linked_title
from crawling.JP.wikipedia_client import WikipediaClient, WikipediaHtmlClient, first_page


TOKYO_PREFECTURE_ID: Final[str] = "JP-13"
type PagePayload = dict[str, str | list[dict[str, str | float]]]


class TargetInputError(ValueError):
    pass


class NonTokyoCityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PageTarget:
    title: str
    lang: str = "ko"
    prefecture_id: str = ""


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
        raise TargetInputError("Input file must be a JSON array of city page titles or target objects.")
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
            raise TargetInputError("Input file must contain strings or objects with a title field.")
    return targets


def acquire_city_data(
    titles: list[str] | list[PageTarget],
    output_dir: Path,
    client: WikipediaClient | None = None,
    source_lang: str = "ko",
) -> tuple[list[PrefectureRecord], list[CityRecord]]:
    wikipedia = client or WikipediaHtmlClient()
    collected_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    city_records: list[CityRecord] = []
    prefectures_by_id: dict[str, PrefectureRecord] = {}
    targets = _coerce_targets(titles, source_lang)
    prefetched_pages = _prefetch_source_pages(wikipedia, targets)
    prefetched_linked_pages = _prefetch_linked_pages(wikipedia, prefetched_pages)

    for target in targets:
        pages = collect_pages(
            wikipedia,
            target,
            prefetched_pages.get((target.lang, target.title)),
            prefetched_linked_pages,
        )
        city = build_city_record(pages, collected_at, fallback_prefecture_id=target.prefecture_id)
        if city.prefecture_id != TOKYO_PREFECTURE_ID:
            raise NonTokyoCityError(
                f"First implementation target is limited to Tokyo Metropolis cities: {target.lang}:{target.title}"
            )
        city_records.append(city)

        prefecture = find_prefecture(city.prefecture_id)
        if prefecture is not None and prefecture.prefecture_id not in prefectures_by_id:
            prefectures_by_id[prefecture.prefecture_id] = build_prefecture_record_for_city(
                wikipedia,
                prefecture,
                collected_at,
                city.source_url,
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    prefecture_records = sorted(prefectures_by_id.values(), key=lambda item: item.prefecture_id)
    city_records = fill_missing_city_climate_tables(city_records, prefecture_records)
    write_json(output_dir / "prefectures.json", prefecture_records)
    write_json(output_dir / "cities.json", city_records)
    return prefecture_records, city_records


def collect_pages(
    client: WikipediaClient,
    target: PageTarget,
    prefetched_source_page: dict | None = None,
    prefetched_linked_pages: dict[tuple[str, str], dict] | None = None,
) -> dict[str, dict]:
    source_page = prefetched_source_page or first_page(client.fetch_page(target.lang, target.title))
    if target.lang == "ko":
        ja_page = _linked_title_stub(source_page, "ja")
        if not _has_coordinates(source_page) and not _has_coordinate_template(source_page):
            if not _linked_title_from_source(source_page, "ja"):
                source_page = first_page(client.fetch_page(target.lang, target.title)) or source_page
                ja_page = _linked_title_stub(source_page, "ja")
            ja_page = _linked_page_from_source(client, source_page, "ja", target, prefetched_linked_pages)
        pages = {
            "source": source_page,
            "ko": source_page,
            "ja": ja_page,
            "en": _linked_title_stub(source_page, "en"),
        }
        pages["source_meta"] = {"lang": target.lang, "title": target.title}
        return pages
    pages = {
        "source": source_page,
        "ko": source_page
        if target.lang == "ko"
        else _linked_page_from_source(client, source_page, "ko", target, prefetched_linked_pages),
        "ja": source_page
        if target.lang == "ja"
        else _linked_page_from_source(client, source_page, "ja", target, prefetched_linked_pages),
        "en": source_page
        if target.lang == "en"
        else _linked_page_from_source(client, source_page, "en", target, prefetched_linked_pages),
    }
    pages["source_meta"] = {"lang": target.lang, "title": target.title}
    return pages


def _coerce_targets(titles: list[str] | list[PageTarget], source_lang: str) -> list[PageTarget]:
    if not titles:
        return []
    first = titles[0]
    if isinstance(first, PageTarget):
        targets: list[PageTarget] = []
        for title in titles:
            if not isinstance(title, PageTarget):
                raise TargetInputError("Input target list must not mix PageTarget objects and raw titles.")
            targets.append(title)
        return targets
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
                page = first_page(payload)
                if page and not page.get("extract") and not _has_revision_content(page):
                    page = first_page(client.fetch_page(target.lang, target.title))
                pages[(target.lang, target.title)] = page
    return pages


def _has_revision_content(page: dict) -> bool:
    revisions = page.get("revisions", []) or []
    if not revisions:
        return False
    revision = revisions[0]
    slots = revision.get("slots", {})
    main = slots.get("main", {})
    return bool(main.get("content") or revision.get("*"))


def _has_coordinates(page: dict) -> bool:
    return bool(page.get("coordinates"))


def _has_coordinate_template(page: dict) -> bool:
    return "{{좌표|" in _revision_content(page)


def _revision_content(page: dict) -> str:
    revisions = page.get("revisions", []) or []
    if not revisions:
        return ""
    revision = revisions[0]
    slots = revision.get("slots", {})
    main = slots.get("main", {})
    return str(main.get("content") or revision.get("*") or "")


def _prefetch_linked_pages(
    client: WikipediaClient,
    source_pages: dict[tuple[str, str], dict],
) -> dict[tuple[str, str], dict]:
    fetch_pages = getattr(client, "fetch_pages", None)
    if fetch_pages is None:
        return {}
    linked_titles_by_lang: dict[str, list[str]] = {}
    for source_page in source_pages.values():
        linked_title = _linked_title_from_source(source_page, "ko")
        if linked_title:
            linked_titles_by_lang.setdefault("ko", []).append(linked_title)

    pages: dict[tuple[str, str], dict] = {}
    for lang, titles in linked_titles_by_lang.items():
        unique_titles = list(dict.fromkeys(titles))
        title_payloads = fetch_pages(lang, unique_titles)
        for title in unique_titles:
            payload = title_payloads.get(title)
            if payload:
                pages[(lang, title)] = first_page(payload)
    return pages


def _linked_page_from_source(
    client: WikipediaClient,
    source_page: dict,
    target_lang: str,
    target: PageTarget,
    prefetched_linked_pages: dict[tuple[str, str], dict] | None = None,
) -> PagePayload:
    linked_title = _linked_title_from_source(source_page, target_lang)
    if linked_title and prefetched_linked_pages:
        prefetched = prefetched_linked_pages.get((target_lang, linked_title))
        if prefetched:
            return prefetched
    if target_lang == "en" and linked_title:
        return {"title": linked_title}
    if linked_title:
        return first_page(client.fetch_page(target_lang, linked_title))
    return {}


def _linked_title_from_source(source_page: dict, target_lang: str) -> str:
    for link in source_page.get("langlinks", []) or []:
        linked_title = str(link.get("title") or "")
        if link.get("lang") == target_lang and linked_title and is_valid_linked_title(target_lang, linked_title):
            return linked_title
    return ""


def _linked_title_stub(source_page: dict, target_lang: str) -> PagePayload:
    linked_title = _linked_title_from_source(source_page, target_lang)
    if linked_title:
        return {"title": linked_title}
    return {}


def write_json(path: Path, records: list[NormalizedRecord]) -> None:
    payload = [asdict(record) for record in records]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# 파일 이력
# 2026-06-04: CLI 모듈에서 파이프라인 오케스트레이션을 분리했다.
