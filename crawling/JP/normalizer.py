"""
도시 및 도도부현 정규화 도우미.

이 파일은 Wikipedia 페이지 페이로드를 정규화된 레코드로 변환한다.
"""

from __future__ import annotations

import re
import hashlib
import unicodedata
import urllib.parse
from typing import Any

from crawling.JP.korean_names import korean_name_for_japanese_title
from crawling.JP.models import (
    STATUS_COLLECTED,
    STATUS_MISSING,
    STATUS_NEEDS_REVIEW,
    CityRecord,
    PrefectureRecord,
    PrefectureReference,
)
from crawling.JP.prefectures import detect_prefecture, find_prefecture


def build_city_record(
    pages: dict[str, dict[str, Any]],
    collected_at: str,
    fallback_prefecture_id: str = "",
) -> CityRecord:
    ko_page = pages["ko"]
    ja_page = pages["ja"]
    en_page = pages["en"]
    source_page = pages.get("source") or ko_page or ja_page or en_page
    source_lang = str(pages.get("source_meta", {}).get("lang") or "ko")
    source_title = str(pages.get("source_meta", {}).get("title") or source_page.get("title") or "")
    ko_extract = str(ko_page.get("extract", ""))
    ja_extract = str(ja_page.get("extract", ""))
    en_extract = str(en_page.get("extract", ""))
    source_extract = str(source_page.get("extract", ""))
    source_content = _revision_content(source_page)
    ko_title = (
        str(ko_page.get("title") or "")
        or (source_title if source_lang == "ko" else "")
        or korean_name_for_japanese_title(str(source_page.get("title") or ""))
    )
    ko_title = _display_korean_title(ko_title)
    description = _lead_description(ko_extract or (source_extract if source_lang == "ko" else ""))
    if not description:
        ko_content = _revision_content(ko_page)
        source_ko_content = source_content if source_lang == "ko" else ""
        description = _lead_description_from_content(ko_content or source_ko_content)
    if not description and ko_title:
        description = f"{ko_title}는 일본 도쿄도에 속한 지자체이다."
    coordinates = (
        _coordinates(source_page)
        or _coordinates(ko_page)
        or _coordinates(ja_page)
        or _coordinates(en_page)
        or _coordinates_from_content(source_content)
        or _coordinates_from_content(_revision_content(ko_page))
        or _coordinates_from_content(_revision_content(ja_page))
        or _coordinates_from_content(_revision_content(en_page))
    )
    geography_description = _section_description(_revision_content(ko_page), ("지리", "Geography", "地理"))
    if not geography_description:
        geography_description = _section_description(source_content, ("지리", "Geography", "地理"))
    if not geography_description:
        geography_description = _korean_geography_fallback(ko_title, prefecture_name="도쿄도", coordinates=coordinates)
    climate_table = (
        _climate_table(source_page)
        or _climate_table(ko_page)
        or _climate_table(ja_page)
        or _climate_table(en_page)
        or _manual_required_climate_table()
    )
    prefecture = find_prefecture(fallback_prefecture_id) if fallback_prefecture_id else None
    if prefecture is None:
        prefecture = detect_prefecture(
            [ko_extract, ja_extract, en_extract, source_extract, str(source_page.get("title", ""))]
        )
    source_url = page_url(source_lang, str(source_page.get("title") or source_title))

    city = CityRecord(
        city_id=_city_id(prefecture, en_page, ko_page, ko_title),
        city_name_ko=ko_title,
        city_name_ja=str(ja_page.get("title") or ""),
        city_name_en=str(en_page.get("title") or ""),
        prefecture_id=prefecture.prefecture_id if prefecture else "",
        location=_location(prefecture),
        latitude=coordinates[0] if coordinates else None,
        longitude=coordinates[1] if coordinates else None,
        description=description,
        geography_description=geography_description,
        climate_table=climate_table,
        site_urls=_site_urls(source_page, ko_page, ja_page, en_page),
        source_name="Wikipedia",
        source_url=source_url,
        collected_at=collected_at,
        field_status={},
        data_confidence="medium" if prefecture and coordinates else "low",
    )
    city.field_status = city_field_status(city, has_korean_page=bool(ko_page.get("title")))
    return city


def build_prefecture_record(
    prefecture: PrefectureReference,
    collected_at: str,
    source_url: str,
) -> PrefectureRecord:
    record = PrefectureRecord(
        prefecture_id=prefecture.prefecture_id,
        name_ko=prefecture.name_ko,
        name_ja=prefecture.name_ja,
        name_en=prefecture.name_en,
        region=prefecture.region,
        source_name="Wikipedia",
        source_url=source_url,
        collected_at=collected_at,
        field_status={},
        data_confidence="medium",
    )
    record.field_status = {
        "prefecture_id": STATUS_COLLECTED,
        "name_ko": STATUS_COLLECTED,
        "name_ja": STATUS_COLLECTED,
        "name_en": STATUS_COLLECTED,
        "region": STATUS_COLLECTED,
    }
    return record


def city_field_status(city: CityRecord, has_korean_page: bool = True) -> dict[str, str]:
    return {
        "city_name_ko": STATUS_NEEDS_REVIEW if city.city_name_ko and not has_korean_page else _status(city.city_name_ko),
        "city_name_ja": _status(city.city_name_ja),
        "city_name_en": _status(city.city_name_en),
        "prefecture_id": _status(city.prefecture_id),
        "location": _status(city.location),
        "latitude": _status(city.latitude),
        "longitude": _status(city.longitude),
        "description": _status(city.description, review_if_present=True),
        "geography_description": _status(city.geography_description),
        "climate_table": _climate_status(city.climate_table),
        "site_urls": _status(city.site_urls),
    }


def page_url(lang: str, title: str) -> str:
    if not title:
        return ""
    return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def _display_korean_title(title: str) -> str:
    return re.sub(r"\s+\(도쿄도\)$", "", title).strip()


def _coordinates(page: dict[str, Any]) -> tuple[float, float] | None:
    coordinates = page.get("coordinates", []) or []
    if not coordinates:
        return None
    first = coordinates[0]
    lat = first.get("lat")
    lon = first.get("lon")
    if isinstance(lat, int | float) and isinstance(lon, int | float):
        return float(lat), float(lon)
    return None


def _coordinates_from_content(content: str) -> tuple[float, float] | None:
    if not content:
        return None
    match = re.search(
        r"\{\{좌표\|"
        r"([0-9.]+)\|([0-9.]+)?\|?([0-9.]+)?\|?([NS])\|"
        r"([0-9.]+)\|([0-9.]+)?\|?([0-9.]+)?\|?([EW])",
        content,
    )
    if not match:
        return None
    lat = _dms_to_decimal(match.group(1), match.group(2), match.group(3), match.group(4))
    lon = _dms_to_decimal(match.group(5), match.group(6), match.group(7), match.group(8))
    return lat, lon


def _dms_to_decimal(degrees: str, minutes: str | None, seconds: str | None, direction: str) -> float:
    value = float(degrees)
    if minutes:
        value += float(minutes) / 60
    if seconds:
        value += float(seconds) / 3600
    if direction in ("S", "W"):
        value *= -1
    return value


def _site_urls(*pages: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for page in pages:
        for item in page.get("extlinks", []) or []:
            url = str(item.get("url") or "")
            lowered = url.lower()
            if not url or "blog" in lowered or "sns" in lowered:
                continue
            if not _is_official_or_tourism_url(lowered):
                continue
            if url not in urls:
                urls.append(url)
            if len(urls) == 2:
                return urls
    return urls


def _lead_description(extract: str) -> str:
    paragraphs = [" ".join(paragraph.split()) for paragraph in re.split(r"\n\s*\n", extract) if paragraph.strip()]
    return "\n\n".join(paragraphs)


def _lead_description_from_content(content: str) -> str:
    if not content:
        return ""
    heading = re.search(r"(?m)^==\s*[^=].*?==\s*$", content)
    lead = content[: heading.start()] if heading else content
    return _clean_section_text(lead)


def _climate_table(page: dict[str, Any]) -> dict[str, str] | None:
    content = _revision_content(page)
    if not content:
        return None
    section_content = _clean_section_text(_section_content(content, ("기후", "Climate", "気候")))
    section_table = _climate_section_table(content)
    if section_table:
        if section_content:
            section_table["content"] = section_content
        return section_table
    if section_content:
        return {
            "caption": _section_heading(content, ("기후", "Climate", "気候")) or "기후",
            "wikitext": "",
            "content": section_content,
        }
    for table in re.findall(r"(?s)\{\|.*?\n\|\}", content):
        if any(keyword in table for keyword in ("기후", "Climate", "気候")):
            return {
                "caption": _table_caption(table),
                "wikitext": table,
            }
    return None


def _manual_required_climate_table() -> dict[str, str]:
    return {
        "caption": "수작업 필요",
        "wikitext": "",
        "note": "Wikipedia에서 기후 표를 자동 취득하지 못해 수작업 확인이 필요하다.",
    }


def _climate_section_table(content: str) -> dict[str, str] | None:
    heading = re.search(r"(?m)^==+\s*(기후|Climate|気候)\s*==+\s*$", content)
    if not heading:
        return None
    section_start = heading.end()
    next_heading = re.search(r"(?m)^==\s*[^=].*?==\s*$", content[section_start:])
    section_end = section_start + next_heading.start() if next_heading else len(content)
    section = content[section_start:section_end]
    table_match = re.search(r"(?s)\{\|.*?\n\|\}", section)
    if not table_match:
        return None
    table = table_match.group(0)
    return {
        "caption": _table_caption(table) or heading.group(1),
        "wikitext": table,
    }


def _revision_content(page: dict[str, Any]) -> str:
    revisions = page.get("revisions", []) or []
    if not revisions:
        return ""
    revision = revisions[0]
    slots = revision.get("slots", {})
    main = slots.get("main", {})
    return str(main.get("content") or revision.get("*") or "")


def _section_description(content: str, headings: tuple[str, ...]) -> str:
    section = _section_content(content, headings)
    if not section:
        return ""
    return _clean_section_text(section)


def _clean_section_text(section: str) -> str:
    without_tables = re.sub(r"(?s)\{\|.*?\n\|\}", "", section)
    without_refs = re.sub(r"<ref.*?</ref>|<ref[^>]*/>", "", without_tables)
    without_templates = _strip_templates(without_refs)
    without_links = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", without_templates)
    without_html = re.sub(r"<[^>]+>", "", without_links)
    without_markup = re.sub(r"'{2,}", "", without_html)
    without_markup = re.sub(r"\(\s*\)", "", without_markup)
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", without_markup):
        lines = [
            line.strip()
            for line in paragraph.splitlines()
            if line.strip() and not line.strip().startswith(("==", "|", "!", "{", "}"))
        ]
        if lines:
            paragraphs.append(" ".join(lines))
    return "\n\n".join(paragraphs)


def _strip_templates(text: str) -> str:
    result: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        pair = text[index : index + 2]
        if pair == "{{":
            depth += 1
            index += 2
            continue
        if pair == "}}" and depth:
            depth -= 1
            index += 2
            continue
        if depth == 0:
            result.append(text[index])
        index += 1
    return "".join(result)


def _section_content(content: str, headings: tuple[str, ...]) -> str:
    escaped = "|".join(re.escape(heading) for heading in headings)
    heading = re.search(rf"(?m)^==+\s*({escaped})\s*==+\s*$", content)
    if not heading:
        return ""
    section_start = heading.end()
    next_heading = re.search(r"(?m)^==\s*[^=].*?==\s*$", content[section_start:])
    section_end = section_start + next_heading.start() if next_heading else len(content)
    return content[section_start:section_end]


def _section_heading(content: str, headings: tuple[str, ...]) -> str:
    escaped = "|".join(re.escape(heading) for heading in headings)
    heading = re.search(rf"(?m)^==+\s*({escaped})\s*==+\s*$", content)
    if not heading:
        return ""
    return heading.group(1)


def _table_caption(table: str) -> str:
    match = re.search(r"^\|\+\s*(.+)$", table, re.MULTILINE)
    if not match:
        return ""
    return re.sub(r"<.*?>", "", match.group(1)).strip()


def _location(prefecture: PrefectureReference | None) -> str:
    if prefecture is None:
        return ""
    return f"일본 {prefecture.name_ko}"


def _korean_geography_fallback(
    city_name_ko: str,
    prefecture_name: str,
    coordinates: tuple[float, float] | None,
) -> str:
    if not city_name_ko:
        return ""
    if coordinates:
        return (
            f"{city_name_ko}는 일본 {prefecture_name}에 위치한 지자체이며, "
            f"대표 좌표는 위도 {coordinates[0]}, 경도 {coordinates[1]}이다."
        )
    return f"{city_name_ko}는 일본 {prefecture_name}에 위치한 지자체이다."


def _city_id(
    prefecture: PrefectureReference | None,
    en_page: dict[str, Any],
    ko_page: dict[str, Any],
    fallback_title: str = "",
) -> str:
    name = str(en_page.get("title") or ko_page.get("title") or fallback_title or "unknown")
    romanized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", romanized).strip("-").upper()
    if not slug:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8].upper()
        slug = f"KO-{digest}"
    prefix = prefecture.prefecture_id if prefecture else "JP-UNKNOWN"
    return f"{prefix}-{slug}"


def _is_official_or_tourism_url(lowered_url: str) -> bool:
    return any(
        token in lowered_url
        for token in (
            ".lg.jp",
            ".or.jp",
            "city.",
            "town.",
            "village.",
            "kankou",
            "tourism",
        )
    )


def _status(value: str | int | float | list[str] | None, review_if_present: bool = False) -> str:
    if value is None or value == "":
        return STATUS_MISSING
    if review_if_present:
        return STATUS_NEEDS_REVIEW
    return STATUS_COLLECTED


def _climate_status(value: dict[str, str] | None) -> str:
    if not value:
        return STATUS_MISSING
    if value.get("caption") == "수작업 필요":
        return STATUS_NEEDS_REVIEW
    return STATUS_COLLECTED


# 파일 이력
# 2026-06-04: CLI 모듈에서 도시 정규화를 분리했다.
