import time
import requests
import hashlib
import re
import unicodedata
import urllib.parse
from typing import Any

from crawling.KR.models import (
    STATUS_COLLECTED,
    STATUS_MISSING,
    STATUS_NEEDS_REVIEW,
    CityRecord,
    PrefectureRecord,
    ProvinceReference,
)
from crawling.KR.provinces import MUNICIPALITY_EN_MAP, detect_province, find_province


def _geocode_nominatim(address: str) -> tuple[float, float] | None:
    try:
        # Nominatim usage policy requires respecting rate limits (1 req/sec)
        time.sleep(1.0)
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "LovvCityAcquisition/0.1"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        res_json = response.json()
        if res_json:
            lat = float(res_json[0]["lat"])
            lon = float(res_json[0]["lon"])
            return lat, lon
    except Exception as e:
        print(f"Warning: Nominatim geocoding failed for '{address}': {e}")
    return None


def build_city_record(
    pages: dict[str, dict[str, Any]],
    collected_at: str,
    fallback_prefecture_id: str = "",
) -> CityRecord:
    # Since we only crawl Korean Wikipedia, pages["ko"] is the primary source
    ko_page = pages.get("ko") or pages.get("source") or {}
    source_title = str(ko_page.get("title") or "")
    
    ko_extract = str(ko_page.get("extract", ""))
    source_content = _revision_content(ko_page)
    
    # Extract Korean clean title
    ko_title = _display_korean_title(source_title)
    
    # 1. Description (Lead Paragraphs)
    description = _lead_description(ko_extract)
    if not description:
        description = _lead_description_from_content(source_content)
    
    # 2. Coordinates
    coordinates = (
        _coordinates(ko_page)
        or _coordinates_from_content(source_content)
    )
    
    # 3. Geography Description
    geography_description = _section_description(source_content, ("지리", "Geography"))
    
    # Determine Province (Prefecture)
    province = find_province(fallback_prefecture_id) if fallback_prefecture_id else None
    if province is None:
        province = detect_province([ko_extract, source_title])
        
    province_name = province.name_ko if province else "한국"
    
    # Fallback to Nominatim geocoding if Wikipedia coordinates are missing
    if not coordinates and ko_title:
        address = f"대한민국 {province_name} {ko_title}"
        coords = _geocode_nominatim(address)
        if coords:
            coordinates = coords
            
    # 4. Climate Table
    climate_table = (
        _climate_table(ko_page)
        or _manual_required_climate_table()
    )
    
    # Finalize description and geography description defaults
    if not description and ko_title:
        description = f"{ko_title}는 대한민국 {province_name}에 속한 지자체이다."
        
    if not geography_description:
        geography_description = _korean_geography_fallback(ko_title, province_name=province_name, coordinates=coordinates)
        
    # Translate and Map English/Japanese Names (Korean Only Scope)
    # city_name_ja is left empty as requested
    city_name_ja = ""
    # Map city_name_en locally using MUNICIPALITY_EN_MAP
    city_name_en = MUNICIPALITY_EN_MAP.get(ko_title, "")
    if not city_name_en:
        city_name_en = MUNICIPALITY_EN_MAP.get(source_title, "")
        
    source_url = page_url("ko", source_title)
    
    # 5. Site URLs (Official municipal websites)
    site_urls = _site_urls(ko_page)
    
    city = CityRecord(
        city_id=_city_id(province, city_name_en, ko_title),
        city_name_ko=ko_title,
        city_name_ja=city_name_ja,
        city_name_en=city_name_en,
        prefecture_id=province.prefecture_id if province else "",
        location=_location(province),
        latitude=coordinates[0] if coordinates else None,
        longitude=coordinates[1] if coordinates else None,
        description=description,
        geography_description=geography_description,
        climate_table=climate_table,
        site_urls=site_urls,
        source_name="Wikipedia",
        source_url=source_url,
        collected_at=collected_at,
        field_status={},
        data_confidence="medium" if province and coordinates else "low",
    )
    
    # Assign field status according to spec
    city.field_status = city_field_status(city)
    return city


def build_prefecture_record(
    province: ProvinceReference,
    collected_at: str,
    source_url: str,
) -> PrefectureRecord:
    # Reuses JP's PrefectureRecord structure for database compatibility
    record = PrefectureRecord(
        prefecture_id=province.prefecture_id,
        name_ko=province.name_ko,
        name_ja="",  # Japanese name ignored
        name_en=province.name_en,
        region=province.region,
        source_name="Wikipedia",
        source_url=source_url,
        collected_at=collected_at,
        field_status={},
        data_confidence="medium",
    )
    record.field_status = {
        "prefecture_id": STATUS_COLLECTED,
        "name_ko": STATUS_COLLECTED,
        "name_ja": STATUS_MISSING,
        "name_en": STATUS_COLLECTED,
        "region": STATUS_COLLECTED,
    }
    return record


def city_field_status(city: CityRecord) -> dict[str, str]:
    return {
        "city_name_ko": _status(city.city_name_ko),
        "city_name_ja": STATUS_MISSING,  # Always missing per specs/requirements
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
    return re.sub(r"\s+\([^)]+\)$", "", title).strip()


def _coordinates(page: dict[str, Any]) -> tuple[float, float] | None:
    coordinates = page.get("coordinates", []) or []
    if coordinates:
        first = coordinates[0]
        lat = first.get("lat")
        lon = first.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)
            
    # Try parsing geohack URL in external links
    for item in page.get("extlinks", []) or []:
        url = str(item.get("url") or "")
        if "geohack" in url:
            coords = _parse_geohack_url(url)
            if coords:
                return coords
    return None


def _parse_geohack_url(url: str) -> tuple[float, float] | None:
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        params_list = query.get("params")
        if not params_list:
            return None
        params = params_list[0]
        # Match e.g., 37_45_N_128_54_E or 37_45_12_N_128_54_10_E or 37.75_N_128.9_E
        match = re.search(
            r"([0-9.]+)_([0-9.]+)?_?([0-9.]+)?_?([NS])_([0-9.]+)_([0-9.]+)?_?([0-9.]+)?_?([EW])",
            params,
        )
        if not match:
            return None
        lat = _dms_to_decimal(match.group(1), match.group(2), match.group(3), match.group(4))
        lon = _dms_to_decimal(match.group(5), match.group(6), match.group(7), match.group(8))
        return lat, lon
    except Exception:
        return None


def _coordinates_from_content(content: str) -> tuple[float, float] | None:
    if not content:
        return None
    # Parse DMS coordinates template commonly used in Korean Wikipedia, e.g., {{좌표|37|45|N|128|54|E|...}}
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


def _site_urls(page: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for item in page.get("extlinks", []) or []:
        url = str(item.get("url") or "")
        lowered = url.lower()
        if not url or "blog" in lowered or "sns" in lowered or "facebook" in lowered:
            continue
        if not _is_official_or_tourism_url(lowered):
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) == 2:
            return urls
    return urls


def _is_official_or_tourism_url(lowered_url: str) -> bool:
    # Korean local government domains usually contain ".go.kr", and tourism sites contain "tour"
    return any(
        token in lowered_url
        for token in (
            ".go.kr",
            "tour.",
            "tourism",
            "travel",
            "kankou",
        )
    )


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
    if page.get("climate_table"):
        return page["climate_table"]
    content = _revision_content(page)
    if not content:
        return None
    section_content = _clean_section_text(_section_content(content, ("기후", "Climate")))
    section_table = _climate_section_table(content)
    if section_table:
        if section_content:
            section_table["content"] = section_content
        return section_table
    if section_content:
        return {
            "caption": _section_heading(content, ("기후", "Climate")) or "기후",
            "wikitext": "",
            "content": section_content,
        }
    for table in re.findall(r"(?s)\{\|.*?\n\|\}", content):
        if any(keyword in table for keyword in ("기후", "Climate")):
            return {
                "caption": _table_caption(table) or "기후",
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
    heading = re.search(r"(?m)^==+\s*(기후|Climate)\s*==+\s*$", content)
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


def _location(province: ProvinceReference | None) -> str:
    if province is None:
        return ""
    return f"대한민국 {province.name_ko}"


def _korean_geography_fallback(
    city_name_ko: str,
    province_name: str,
    coordinates: tuple[float, float] | None,
) -> str:
    if not city_name_ko:
        return ""
    if coordinates:
        return (
            f"{city_name_ko}는 대한민국 {province_name}에 위치한 지자체이며, "
            f"대표 좌표는 위도 {coordinates[0]}, 경도 {coordinates[1]}이다."
        )
    return f"{city_name_ko}는 대한민국 {province_name}에 위치한 지자체이다."


def _city_id(
    province: ProvinceReference | None,
    city_name_en: str,
    fallback_title: str = "",
) -> str:
    name = city_name_en or fallback_title or "unknown"
    romanized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", romanized).strip("-").upper()
    if not slug:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8].upper()
        slug = f"KO-{digest}"
    prefix = province.prefecture_id if province else "KR-UNKNOWN"
    return f"{prefix}-{slug}"


def _status(value: object, review_if_present: bool = False) -> str:
    if value is None or value == "" or value == [] or value == {}:
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
