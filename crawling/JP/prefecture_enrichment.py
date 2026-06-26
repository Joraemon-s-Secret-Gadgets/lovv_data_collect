from __future__ import annotations

import re
import urllib.parse
from typing import Final

from crawling.JP.models import (
    STATUS_COLLECTED,
    STATUS_MISSING,
    STATUS_NEEDS_REVIEW,
    PrefectureRecord,
    PrefectureReference,
)
from crawling.JP.normalizer import build_prefecture_record
from crawling.JP.wikipedia_client import WikipediaClient, first_page


TOKYO_PREFECTURE_SOURCE_LANG: Final[str] = "ko"
TOKYO_PREFECTURE_SOURCE_TITLE: Final[str] = "도쿄도"

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type PagePayload = dict[str, JsonValue]
type ClimateTable = dict[str, str]


def build_tokyo_prefecture_record(
    prefecture: PrefectureReference,
    source_page: PagePayload,
    collected_at: str,
) -> PrefectureRecord:
    content = _revision_content(source_page)
    description = _lead_description(_text(source_page.get("extract"))) or _lead_description_from_content(content)
    climate_table = _climate_table(source_page) or _manual_required_climate_table()
    coordinates = _coordinates(source_page)
    record = PrefectureRecord(
        prefecture_id=prefecture.prefecture_id,
        name_ko=prefecture.name_ko,
        name_ja=prefecture.name_ja,
        name_en=prefecture.name_en,
        region=prefecture.region,
        latitude=coordinates[0] if coordinates else None,
        longitude=coordinates[1] if coordinates else None,
        description=description,
        geography_description=_section_description(content, ("지리",)),
        climate_table=climate_table,
        source_name="Wikipedia",
        source_url=page_url(TOKYO_PREFECTURE_SOURCE_LANG, TOKYO_PREFECTURE_SOURCE_TITLE),
        collected_at=collected_at,
        field_status={},
        data_confidence="medium",
    )
    record.field_status = prefecture_field_status(record)
    return record


def build_prefecture_record_for_city(
    client: WikipediaClient,
    prefecture: PrefectureReference,
    collected_at: str,
    fallback_source_url: str,
) -> PrefectureRecord:
    if prefecture.prefecture_id == "JP-13":
        source_page = _tokyo_prefecture_page(client)
        if source_page:
            return build_tokyo_prefecture_record(prefecture, source_page, collected_at)
    return build_prefecture_record(
        prefecture=prefecture,
        collected_at=collected_at,
        source_url=fallback_source_url,
    )


def prefecture_field_status(record: PrefectureRecord) -> dict[str, str]:
    return {
        "prefecture_id": _status(record.prefecture_id),
        "name_ko": _status(record.name_ko),
        "name_ja": _status(record.name_ja),
        "name_en": _status(record.name_en),
        "region": _status(record.region),
        "latitude": _status(record.latitude),
        "longitude": _status(record.longitude),
        "description": _status(record.description, review_if_present=True),
        "geography_description": _status(record.geography_description),
        "climate_table": _climate_status(record.climate_table),
    }


def page_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def _tokyo_prefecture_page(client: WikipediaClient) -> PagePayload:
    fetch_pages = getattr(client, "fetch_pages", None)
    if fetch_pages is not None:
        try:
            payload = fetch_pages(TOKYO_PREFECTURE_SOURCE_LANG, [TOKYO_PREFECTURE_SOURCE_TITLE]).get(
                TOKYO_PREFECTURE_SOURCE_TITLE
            )
        except KeyError:
            return {}
        if payload:
            return first_page(payload)
    try:
        return first_page(client.fetch_page(TOKYO_PREFECTURE_SOURCE_LANG, TOKYO_PREFECTURE_SOURCE_TITLE))
    except KeyError:
        return {}


def _text(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    return ""


def _coordinates(page: PagePayload) -> tuple[float, float] | None:
    coordinates = page.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        return None
    first = coordinates[0]
    if not isinstance(first, dict):
        return None
    lat = first.get("lat")
    lon = first.get("lon")
    if isinstance(lat, int | float) and isinstance(lon, int | float):
        return float(lat), float(lon)
    return None


def _lead_description(extract: str) -> str:
    paragraphs = [" ".join(paragraph.split()) for paragraph in re.split(r"\n\s*\n", extract) if paragraph.strip()]
    return "\n\n".join(paragraphs)


def _lead_description_from_content(content: str) -> str:
    if not content:
        return ""
    heading = re.search(r"(?m)^==\s*[^=].*?==\s*$", content)
    lead = content[: heading.start()] if heading else content
    return _clean_section_text(lead)


def _section_description(content: str, headings: tuple[str, ...]) -> str:
    section = _section_content(content, headings)
    if not section:
        return ""
    return _clean_section_text(section)


def _climate_table(page: PagePayload) -> ClimateTable | None:
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
    return None


def _manual_required_climate_table() -> ClimateTable:
    return {
        "caption": "수작업 필요",
        "wikitext": "",
        "note": "Wikipedia에서 기후 표를 자동 취득하지 못해 수작업 확인이 필요하다.",
    }


def _climate_section_table(content: str) -> ClimateTable | None:
    heading = re.search(r"(?m)^==+\s*(기후|Climate|気候)\s*==+\s*$", content)
    if not heading:
        return None
    section_start = heading.end()
    next_heading = re.search(r"(?m)^==+\s*[^=].*?==+\s*$", content[section_start:])
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


def _revision_content(page: PagePayload) -> str:
    revisions = page.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        return ""
    revision = revisions[0]
    if not isinstance(revision, dict):
        return ""
    slots = revision.get("slots")
    if not isinstance(slots, dict):
        return _text(revision.get("*"))
    main = slots.get("main")
    if not isinstance(main, dict):
        return ""
    return _text(main.get("content"))


def _section_content(content: str, headings: tuple[str, ...]) -> str:
    escaped = "|".join(re.escape(heading) for heading in headings)
    heading = re.search(rf"(?m)^==+\s*({escaped})\s*==+\s*$", content)
    if not heading:
        return ""
    section_start = heading.end()
    next_heading = re.search(r"(?m)^==+\s*[^=].*?==+\s*$", content[section_start:])
    section_end = section_start + next_heading.start() if next_heading else len(content)
    return content[section_start:section_end]


def _section_heading(content: str, headings: tuple[str, ...]) -> str:
    escaped = "|".join(re.escape(heading) for heading in headings)
    heading = re.search(rf"(?m)^==+\s*({escaped})\s*==+\s*$", content)
    if not heading:
        return ""
    return heading.group(1)


def _clean_section_text(section: str) -> str:
    without_tables = re.sub(r"(?s)\{\|.*?\n\|\}", "", section)
    without_refs = re.sub(r"<ref.*?</ref>|<ref[^>]*/>", "", without_tables)
    without_templates = _strip_templates(without_refs)
    without_links = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", without_templates)
    without_html = re.sub(r"<[^>]+>", "", without_links)
    without_markup = re.sub(r"'{2,}", "", without_html)
    without_markup = re.sub(r"\(\s*\)", "", without_markup)
    paragraphs: list[str] = []
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


def _table_caption(table: str) -> str:
    match = re.search(r"^\|\+\s*(.+)$", table, re.MULTILINE)
    if not match:
        return ""
    return re.sub(r"<.*?>", "", match.group(1)).strip()


def _status(value: str | int | float | None, review_if_present: bool = False) -> str:
    if value is None or value == "":
        return STATUS_MISSING
    if review_if_present:
        return STATUS_NEEDS_REVIEW
    return STATUS_COLLECTED


def _climate_status(value: ClimateTable | None) -> str:
    if not value:
        return STATUS_MISSING
    if value.get("caption") == "수작업 필요":
        return STATUS_NEEDS_REVIEW
    return STATUS_COLLECTED
