"""Domain-specific preprocessing for KR raw detail payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kr_details_pipeline.transform import build_city_record


@dataclass
class SubtypeMappingResult:
    """Result of deterministic attraction subtype mapping."""

    success: bool
    code: str | None  # attraction_subtype_code
    name: str | None  # attraction_subtype_name
    source: str | None  # classification_source = "lcls_systm3"
    version: str | None  # classification_mapping_version = ISO date


@dataclass
class FestivalSourceFields:
    """Result of festival source classification preservation."""

    source_subtype_name: str | None
    source_theme: str | None
    program: str | None
    subevent: str | None


KR_BOUNDS = {
    "lon_min": 124.0,
    "lon_max": 132.0,
    "lat_min": 33.0,
    "lat_max": 39.0,
}

COMMON_KEYS = {
    "PK",
    "SK",
    "entity_id",
    "entity_type",
    "content_id",
    "contenttypeid",
    "city_id",
    "city_name_en",
    "city_name_ko",
    "province",
    "province_key",
    "city_key",
    "domain_sort_key",
    "title",
    "address",
    "longitude",
    "latitude",
    "image_url",
    "description",
    "homepage",
    "zipcode",
    "copyright_type",
    "created_time",
    "modified_time",
    "quality_status",
    "review_queues",
    "source_key",
    "lcls_systm3",
    "source_type",
    "raw_s3_uri",
}

CITY_METADATA_KEYS = {
    "PK",
    "SK",
    "entity_id",
    "entity_type",
    "city_id",
    "city_name_en",
    "city_name_ko",
    "province",
    "province_key",
    "city_key",
    "domain_sort_key",
    "sigungus_included",
    "scraped_at",
    "quality_status",
    "review_queues",
    "source_key",
}

VISITOR_STATISTICS_KEYS = {
    "PK",
    "SK",
    "entity_id",
    "entity_type",
    "city_id",
    "city_name_en",
    "city_name_ko",
    "province",
    "province_key",
    "city_key",
    "domain_sort_key",
    "year",
    "month",
    "days",
    "locals_total",
    "locals_daily_avg",
    "out_of_town_total",
    "out_of_town_daily_avg",
    "foreigners_total",
    "foreigners_daily_avg",
    "total_visitors",
    "total_daily_avg",
    "annual_totals",
    "annual_daily_averages",
    "quality_status",
    "review_queues",
    "source_key",
}

DOMAIN_KEYS = {
    "attraction": COMMON_KEYS
    | {
        "theme",
        "theme_tags",
        "phone",
        "opening_hours",
        "closed_days",
        "experience_guide",
        "parking",
        "season_tags",
        "attraction_subtype_code",
        "attraction_subtype_name",
        "classification_source",
        "classification_mapping_version",
    },
    "festival": COMMON_KEYS
    | {
        "event_start_date",
        "event_end_date",
        "month",
        "season",
        "season_tags",
        "visit_months",
        "venue",
        "organizer",
        "organizer_phone",
        "playtime",
        "fee_text",
        "source_subtype_name",
        "source_theme",
        "program",
        "subevent",
        "theme",
        "theme_tags",
        "gsi_sk",
    },
    "city_metadata": CITY_METADATA_KEYS,
    "visitor_statistics": VISITOR_STATISTICS_KEYS,
}


def extract_lcls_systm3(record: dict[str, Any], detail: dict[str, Any]) -> str | None:
    """common.lclsSystm3 우선, 없으면 record 최상위 lclsSystm3 사용.

    Returns the lcls_systm3 classification code by checking:
    1. detail["common"]["lclsSystm3"] (primary source)
    2. record["lclsSystm3"] (fallback)
    Returns None when both sources are absent or empty.
    """
    common = detail.get("common") if isinstance(detail.get("common"), dict) else {}
    value = str(common.get("lclsSystm3") or "").strip()
    if value:
        return value
    value = str(record.get("lclsSystm3") or "").strip()
    if value:
        return value
    return None


def _load_classification_dict() -> dict[str, Any]:
    """Load classification_dict.json from the package directory."""
    path = Path(__file__).parent / "classification_dict.json"
    return json.loads(path.read_text(encoding="utf-8"))


def map_attraction_subtype(
    lcls_systm3: str | None,
    classification_dict: dict[str, Any],
) -> SubtypeMappingResult:
    """결정론적 subtype 매핑. 성공 시 code/name/source/version 반환."""
    if not lcls_systm3:
        return SubtypeMappingResult(success=False, code=None, name=None, source=None, version=None)

    mappings = classification_dict.get("mappings", {})
    entry = mappings.get(lcls_systm3)

    if entry is None or entry.get("type") != "Attraction":
        return SubtypeMappingResult(success=False, code=None, name=None, source=None, version=None)

    version = classification_dict.get("version", "")
    return SubtypeMappingResult(
        success=True,
        code=entry["code"],
        name=entry["name"],
        source="lcls_systm3",
        version=version,
    )


def preserve_festival_source(
    lcls_systm3: str | None,
    classification_dict: dict[str, Any],
    intro: dict[str, Any],
) -> FestivalSourceFields:
    """축제 원천 분류와 프로그램 정보 보존.

    Looks up lcls_systm3 in classification_dict mappings to extract
    source_subtype_name and source_theme. Also preserves program and
    subevent from intro fields when non-empty.

    Returns FestivalSourceFields with None for fields that cannot be resolved.
    """
    source_subtype_name: str | None = None
    source_theme: str | None = None

    if lcls_systm3:
        mappings = classification_dict.get("mappings", {})
        entry = mappings.get(lcls_systm3)
        if entry is not None:
            source_subtype_name = entry.get("name")
            source_theme = entry.get("theme")

    # Preserve program if non-null and non-empty
    raw_program = str(intro.get("program") or "").strip()
    program = raw_program if raw_program else None

    # Preserve subevent if non-null and non-empty
    raw_subevent = str(intro.get("subevent") or "").strip()
    subevent = raw_subevent if raw_subevent else None

    return FestivalSourceFields(
        source_subtype_name=source_subtype_name,
        source_theme=source_theme,
        program=program,
        subevent=subevent,
    )


def build_festival_gsi_sk(content_id: str, event_start_date: str | None) -> str:
    """Build GSI Sort Key for festival monthly lookup.

    Format: FESTIVAL#{month:02d}#{content_id}
    - Uses event_start_date month
    - Defaults to 00 when event_start_date is missing or unparseable
    - For multi-month festivals, uses start month only

    Args:
        content_id: Festival content ID.
        event_start_date: ISO date string (YYYY-MM-DD) or empty/None.

    Returns:
        GSI SK string, e.g., "FESTIVAL#10#2002"
    """
    if event_start_date and len(event_start_date) >= 7:
        try:
            month = int(event_start_date[5:7])
        except (ValueError, IndexError):
            month = 0
    else:
        month = 0
    return f"FESTIVAL#{month:02d}#{content_id}"


def preprocess_city_file(raw_file: Path, output_dir: Path, *, table_name: str = "TourKoreaDomainData") -> dict[str, Any]:
    payload = json.loads(raw_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {raw_file}")

    result = preprocess_city_payload(payload, source_key=str(raw_file), table_name=table_name)
    write_preprocess_output(result, output_dir)
    return result["summary"]


def preprocess_city_payload(payload: dict[str, Any], *, source_key: str, table_name: str) -> dict[str, Any]:
    city_record = build_city_record(payload)
    buckets: dict[str, list[dict[str, Any]]] = {
        "city_metadata": [],
        "visitor_statistics": [],
        "attractions": [],
        "festivals": [],
        "review": [],
        "failed": [],
        "load_items": [],
    }

    city_item = _build_city_metadata_item(payload, city_record, source_key=source_key)
    buckets["city_metadata"].append(city_item)
    buckets["load_items"].append({"table": table_name, **city_item})

    for record, source_array in _iter_raw_content(payload):
        item = _build_domain_item(record, city_record, source_key=source_key, source_array=source_array)
        entity_type = item.get("entity_type")
        status = str(item.get("quality_status") or "")
        if status == "failed":
            buckets["failed"].append(item)
            continue
        if entity_type == "excluded":
            buckets["review"].append(item)
            continue
        if entity_type not in DOMAIN_KEYS:
            buckets["review"].append(item)
            continue

        projected = _project_domain_item(item)
        buckets[f"{entity_type}s"].append(projected)
        buckets["load_items"].append({"table": table_name, **projected})
        if status == "review":
            buckets["review"].append(projected)

    for stat_item in _build_visitor_statistics_items(payload, city_record, source_key=source_key):
        buckets["visitor_statistics"].append(stat_item)
        buckets["load_items"].append({"table": table_name, **stat_item})

    summary = {
        "city_id": city_record["city_id"],
        "city_name_en": city_record["city_name_en"],
        "table_name": table_name,
        "city_metadata": len(buckets["city_metadata"]),
        "visitor_statistics": len(buckets["visitor_statistics"]),
        "attractions": len(buckets["attractions"]),
        "festivals": len(buckets["festivals"]),
        "review": len(buckets["review"]),
        "failed": len(buckets["failed"]),
        "load_items": len(buckets["load_items"]),
    }
    return {"city_record": city_record, "summary": summary, **buckets}


def write_preprocess_output(result: dict[str, Any], output_dir: Path) -> None:
    normalized_dir = output_dir / "normalized"
    load_dir = output_dir / "load"
    quality_dir = output_dir / "quality"
    review_dir = output_dir / "review"
    failed_dir = output_dir / "failed"
    for directory in (normalized_dir, load_dir, quality_dir, review_dir, failed_dir):
        directory.mkdir(parents=True, exist_ok=True)

    _write_jsonl(normalized_dir / "attractions.jsonl", result["attractions"])
    _write_jsonl(normalized_dir / "festivals.jsonl", result["festivals"])
    _write_jsonl(normalized_dir / "city_metadata.jsonl", result["city_metadata"])
    _write_jsonl(normalized_dir / "visitor_statistics.jsonl", result["visitor_statistics"])
    _write_jsonl(load_dir / "tour_korea_domain_items.jsonl", result["load_items"])
    _write_jsonl(review_dir / "domain_review.jsonl", result["review"])
    _write_jsonl(failed_dir / "invalid_records.jsonl", result["failed"])
    (quality_dir / "summary.json").write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _iter_raw_content(payload: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    result: list[tuple[dict[str, Any], str]] = []
    for row in payload.get("attractions") or []:
        if isinstance(row, dict):
            result.append((dict(row), "attractions"))
    for row in payload.get("festivals") or []:
        if isinstance(row, dict):
            item = dict(row)
            item.setdefault("contenttypeid", "15")
            result.append((item, "festivals"))
    return result


def _build_city_metadata_item(payload: dict[str, Any], city_record: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    city_name_en = city_record["city_name_en"]
    province = city_record.get("province", "")
    return {
        "PK": f"CITY#{city_name_en}",
        "SK": "METADATA#city",
        "entity_id": f"CITY-{city_record['city_id']}",
        "entity_type": "city_metadata",
        "city_id": city_record["city_id"],
        "city_name_en": city_name_en,
        "city_name_ko": city_record.get("city_name_ko", ""),
        "province": province,
        "province_key": f"PROVINCE#{province or 'UNKNOWN'}",
        "city_key": f"CITY#{city_name_en}",
        "domain_sort_key": "METADATA#city",
        "sigungus_included": meta.get("sigungus_included") if isinstance(meta.get("sigungus_included"), list) else [],
        "scraped_at": str(meta.get("scraped_at") or ""),
        "quality_status": "passed",
        "review_queues": [],
        "source_key": source_key,
    }


def _build_visitor_statistics_items(payload: dict[str, Any], city_record: dict[str, Any], *, source_key: str) -> list[dict[str, Any]]:
    raw = payload.get("visitor_statistics")
    if not isinstance(raw, dict):
        return []

    year = raw.get("year")
    annual_totals = raw.get("annual_totals") if isinstance(raw.get("annual_totals"), dict) else {}
    annual_daily_averages = raw.get("annual_daily_averages") if isinstance(raw.get("annual_daily_averages"), dict) else {}
    monthly = raw.get("monthly_statistics") if isinstance(raw.get("monthly_statistics"), list) else []
    city_name_en = city_record["city_name_en"]
    province = city_record.get("province", "")
    items: list[dict[str, Any]] = []

    for row in monthly:
        if not isinstance(row, dict):
            continue
        month = _normalize_stat_month(str(row.get("month") or ""))
        if not month:
            continue
        items.append(
            {
                "PK": f"CITY#{city_name_en}",
                "SK": f"STAT#{month}",
                "entity_id": f"STAT-{city_record['city_id']}-{month}",
                "entity_type": "visitor_statistics",
                "city_id": city_record["city_id"],
                "city_name_en": city_name_en,
                "city_name_ko": city_record.get("city_name_ko", ""),
                "province": province,
                "province_key": f"PROVINCE#{province or 'UNKNOWN'}",
                "city_key": f"CITY#{city_name_en}",
                "domain_sort_key": f"STAT#{month}",
                "year": int(year) if isinstance(year, int) or str(year).isdigit() else None,
                "month": month,
                "days": row.get("days"),
                "locals_total": row.get("locals_total"),
                "locals_daily_avg": row.get("locals_daily_avg"),
                "out_of_town_total": row.get("out_of_town_total"),
                "out_of_town_daily_avg": row.get("out_of_town_daily_avg"),
                "foreigners_total": row.get("foreigners_total"),
                "foreigners_daily_avg": row.get("foreigners_daily_avg"),
                "total_visitors": row.get("total_visitors"),
                "total_daily_avg": row.get("total_daily_avg"),
                "annual_totals": annual_totals,
                "annual_daily_averages": annual_daily_averages,
                "quality_status": "passed",
                "review_queues": [],
                "source_key": source_key,
            }
        )
    return items


def _build_domain_item(
    record: dict[str, Any],
    city_record: dict[str, Any],
    *,
    source_key: str,
    source_array: str,
) -> dict[str, Any]:
    content_id = str(record.get("contentid") or "").strip()
    title = str(record.get("title") or "").strip()
    contenttypeid = str(record.get("contenttypeid") or "").strip()
    entity_type = _classify_domain(contenttypeid, source_array)
    issues: list[str] = []

    if not content_id:
        issues.append("missing_contentid")
    if not title:
        issues.append("missing_title")
    if entity_type == "excluded":
        issues.append("source_review")

    detail = record.get("detail") if isinstance(record.get("detail"), dict) else {}
    common = detail.get("common") if isinstance(detail.get("common"), dict) else {}
    intro = detail.get("intro") if isinstance(detail.get("intro"), dict) else {}
    geo_ok, longitude, latitude = _coordinates(record.get("mapx"), record.get("mapy"))
    if not geo_ok:
        issues.append("location_review")

    # Extract source classification fields (Req 1.1, 1.2, 1.3, 1.4, 1.5, 1.6)
    lcls_systm3 = extract_lcls_systm3(record, detail)

    common_item = {
        "entity_type": entity_type,
        "source_key": source_key,
        "city_id": city_record["city_id"],
        "city_name_en": city_record["city_name_en"],
        "city_name_ko": city_record.get("city_name_ko", ""),
        "province": city_record.get("province", ""),
        "province_key": f"PROVINCE#{city_record.get('province', '') or 'UNKNOWN'}",
        "city_key": f"CITY#{city_record['city_name_en']}",
        "PK": f"CITY#{city_record['city_name_en']}",
        "content_id": content_id,
        "contenttypeid": contenttypeid or None,
        "title": title,
        "description": _first_non_empty(str(common.get("overview") or ""), str(intro.get("overview") or "")),
        "image_url": _first_non_empty(str(record.get("firstimage") or ""), str(common.get("firstimage") or ""), str(record.get("firstimage2") or "")),
        "address": _first_non_empty(str(record.get("addr1") or ""), str(intro.get("addr1") or "")),
        "homepage": _first_non_empty(str(common.get("homepage") or ""), str(record.get("homepage") or "")),
        "zipcode": _first_non_empty(str(common.get("zipcode") or ""), str(record.get("zipcode") or "")),
        "copyright_type": _first_non_empty(str(common.get("cpyrhtDivCd") or ""), str(record.get("cpyrhtDivCd") or "")),
        "created_time": _first_non_empty(str(common.get("createdtime") or ""), str(record.get("createdtime") or "")),
        "modified_time": _first_non_empty(str(common.get("modifiedtime") or ""), str(record.get("modifiedtime") or "")),
        "longitude": longitude,
        "latitude": latitude,
        "lcls_systm3": lcls_systm3,
        "source_type": "tourapi",
        "raw_s3_uri": source_key if source_key else "unknown",
        "review_queues": [],
    }

    if entity_type == "festival":
        event_start = _to_iso_date(str(intro.get("eventstartdate") or record.get("eventstartdate") or ""))
        event_end = _to_iso_date(str(intro.get("eventenddate") or record.get("eventenddate") or ""))
        season = _season_from_iso(event_start)

        # Preserve festival source fields (Req 6.1, 6.2, 6.3, 6.4, 6.5)
        classification_dict = _load_classification_dict()
        festival_source = preserve_festival_source(lcls_systm3, classification_dict, intro)

        # Handle missing lcls_systm3 or unmapped code → classification_review
        if not lcls_systm3:
            issues.append("classification_review")
        elif festival_source.source_subtype_name is None and festival_source.source_theme is None:
            # lcls_systm3 exists but not found in classification_dict
            issues.append("classification_review")

        return {
            **common_item,
            "SK": f"FESTIVAL#{content_id}",
            "domain_sort_key": f"FESTIVAL#{content_id}",
            "entity_id": f"FEST-{content_id}",
            "event_start_date": event_start,
            "event_end_date": event_end,
            "month": int(event_start[5:7]) if event_start else None,
            "season": season,
            "season_tags": [season] if season else [],
            "visit_months": _visit_months(event_start, event_end),
            "venue": _first_non_empty(str(intro.get("eventplace") or ""), common_item["address"]),
            "organizer": str(intro.get("sponsor1") or ""),
            "organizer_phone": str(intro.get("sponsor1tel") or ""),
            "playtime": str(intro.get("playtime") or ""),
            "fee_text": str(intro.get("usetimefestival") or ""),
            "source_subtype_name": festival_source.source_subtype_name,
            "source_theme": festival_source.source_theme,
            "program": festival_source.program,
            "subevent": festival_source.subevent,
            "theme": festival_source.source_theme or "",
            "theme_tags": [festival_source.source_theme] if festival_source.source_theme else [],
            "gsi_sk": build_festival_gsi_sk(content_id, event_start),
            "quality_status": _quality_status(issues),
            "review_queues": _dedupe(issues),
        }

    if entity_type == "attraction":
        theme = _first_non_empty(str(record.get("_assigned_theme") or ""), str(intro.get("cat3") or ""), str(record.get("cat3") or ""))
        if not theme:
            issues.append("theme_review")
        phone = _first_non_empty(
            str(record.get("tel") or ""),
            str(common.get("tel") or ""),
            str(intro.get("infocenter") or ""),
            str(intro.get("infocenterculture") or ""),
        )

        # Req 1.5: lcls_systm3 null → classification_review
        if not lcls_systm3:
            issues.append("classification_review")

        # Req 2.1, 2.2, 2.3: Deterministic subtype mapping
        classification_dict = _load_classification_dict()
        subtype_result = map_attraction_subtype(lcls_systm3, classification_dict)

        attraction_item = {
            **common_item,
            "SK": f"ATTRACTION#{content_id}",
            "domain_sort_key": f"ATTRACTION#{content_id}",
            "entity_id": f"ATT-{content_id}",
            "theme": theme,
            "theme_tags": [theme] if theme else [],
            "phone": phone,
            "opening_hours": str(intro.get("usetime") or ""),
            "closed_days": str(intro.get("restdate") or ""),
            "experience_guide": str(intro.get("expguide") or ""),
            "parking": str(intro.get("parking") or ""),
            "season_tags": [],
        }

        if subtype_result.success:
            attraction_item["attraction_subtype_code"] = subtype_result.code
            attraction_item["attraction_subtype_name"] = subtype_result.name
            attraction_item["classification_source"] = subtype_result.source
            attraction_item["classification_mapping_version"] = subtype_result.version
        else:
            # Req 2.3: unmapped code → classification_review
            if "classification_review" not in issues:
                issues.append("classification_review")

        attraction_item["quality_status"] = _quality_status(issues)
        attraction_item["review_queues"] = _dedupe(issues)
        return attraction_item

    return {
        **common_item,
        "SK": f"EXCLUDED#{content_id or 'UNKNOWN'}",
        "domain_sort_key": f"EXCLUDED#{content_id or 'UNKNOWN'}",
        "entity_id": f"EXCLUDED-{content_id or 'UNKNOWN'}",
        "quality_status": "review",
        "review_queues": _dedupe(issues),
    }


def _classify_domain(contenttypeid: str, source_array: str) -> str:
    if source_array == "festivals" or contenttypeid == "15":
        return "festival"
    if contenttypeid == "39":
        return "excluded"
    if contenttypeid in {"12", "14", "28"}:
        return "attraction"
    return "excluded"


def _project_domain_item(item: dict[str, Any]) -> dict[str, Any]:
    entity_type = str(item.get("entity_type") or "")
    allowed = DOMAIN_KEYS[entity_type]
    return {key: value for key, value in item.items() if key in allowed}


def _coordinates(raw_lon: Any, raw_lat: Any) -> tuple[bool, float | None, float | None]:
    try:
        lon = float(raw_lon)
        lat = float(raw_lat)
    except (TypeError, ValueError):
        return False, None, None
    if not (KR_BOUNDS["lon_min"] <= lon <= KR_BOUNDS["lon_max"] and KR_BOUNDS["lat_min"] <= lat <= KR_BOUNDS["lat_max"]):
        return False, lon, lat
    if lon == 0.0 and lat == 0.0:
        return False, lon, lat
    return True, lon, lat


def _quality_status(issues: list[str]) -> str:
    if "missing_contentid" in issues or "missing_title" in issues:
        return "failed"
    if issues:
        return "review"
    return "passed"


def _first_non_empty(*values: str) -> str:
    for value in values:
        value = value.strip()
        if value:
            return value
    return ""


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _to_iso_date(value: str) -> str:
    value = value.strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    return ""


def _season_from_iso(value: str) -> str | None:
    if not value:
        return None
    month = int(value[5:7])
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def _visit_months(start_iso: str, end_iso: str) -> list[int]:
    if not start_iso:
        return []
    start_month = int(start_iso[5:7])
    if not end_iso:
        return [start_month]
    end_month = int(end_iso[5:7])
    if start_month <= end_month:
        return list(range(start_month, end_month + 1))
    return list(range(start_month, 13)) + list(range(1, end_month + 1))


def _normalize_stat_month(value: str) -> str:
    value = value.strip()
    if len(value) == 7 and value[4] == "-":
        return value.replace("-", "")
    if len(value) == 6 and value.isdigit():
        return value
    return ""


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            file.write("\n")
