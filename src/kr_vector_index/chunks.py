"""Build rich embedding text chunks for S3 Vector indexing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from kr_vector_index.metadata import (
    ENRICHMENT_DERIVED_KEYS,
    build_enriched_metadata,
    compact_metadata,
    trim_to_budget,
    validate_metadata,
)

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"


@dataclass(frozen=True)
class VectorChunk:
    key: str
    place_id: str
    embedding_text: str
    metadata: dict[str, Any]


def build_chunk(item: dict[str, Any], *, chunk_no: int = 0) -> VectorChunk:
    entity_type = _normalize_entity_type(str(item.get("entity_type") or "unknown"))
    source_id = str(item.get("content_id") or item.get("entity_id") or _sk_source_id(item) or "unknown")
    place_id = f"{entity_type}#{source_id}"
    key = f"{place_id}#{chunk_no}"
    text = build_embedding_text(item, entity_type=entity_type)
    metadata = compact_metadata(
        {
            "country": "KR",
            "province": item.get("province"),
            "city_id": item.get("city_id"),
            "city_name_en": item.get("city_name_en"),
            "city_name_ko": item.get("city_name_ko"),
            "entity_type": entity_type,
            "source_type": entity_type,
            "source_id": source_id,
            "place_id": place_id,
            "title": item.get("title"),
            "class_tags": _class_tags(item),
            "theme_tags": _tags(item, entity_type),
            "season_tags": item.get("season_tags"),
            "visit_months": item.get("visit_months"),
            "latitude": _number(item.get("latitude")),
            "longitude": _number(item.get("longitude")),
            "raw_s3_uri": item.get("source") or item.get("raw_s3_uri") or "unknown",
            "ddb_pk": item.get("PK"),
            "ddb_sk": item.get("SK"),
            "embedding_model": EMBEDDING_MODEL,
        }
    )

    # Merge enrichment-derived fields for attractions with succeeded enrichment
    if entity_type == "attraction":
        enriched = build_enriched_metadata(item)
        # Only merge enrichment-specific fields to avoid overwriting computed values
        for field in ENRICHMENT_DERIVED_KEYS:
            if field in enriched:
                metadata[field] = enriched[field]
        # Also include attraction_subtype_code if present
        if "attraction_subtype_code" in enriched:
            metadata["attraction_subtype_code"] = enriched["attraction_subtype_code"]

    # Include festival theme fields when classification succeeded
    if entity_type == "festival":
        classification = item.get("festival_theme_classification")
        if isinstance(classification, dict) and classification.get("status") == "succeeded":
            theme_tags = item.get("theme_tags")
            if theme_tags and isinstance(theme_tags, list):
                metadata["theme_tags"] = theme_tags

    # Ensure size compliance before validation
    trimmed = trim_to_budget(metadata)
    if trimmed is None:
        logger.warning(
            "Metadata exceeds budget for item %s after trimming; proceeding without enrichment fields",
            source_id,
        )
        # Remove enrichment fields and retry with base metadata
        for key_to_remove in ENRICHMENT_DERIVED_KEYS:
            metadata.pop(key_to_remove, None)
        trimmed = trim_to_budget(metadata)
        if trimmed is None:
            # Fallback: use metadata as-is, validate_metadata will catch if still too large
            trimmed = metadata

    metadata = validate_metadata(trimmed)
    return VectorChunk(key=key, place_id=place_id, embedding_text=text, metadata=metadata)


def build_chunks(items: list[dict[str, Any]]) -> list[VectorChunk]:
    return [build_chunk(item) for item in items]


def build_embedding_text(item: dict[str, Any], *, entity_type: str) -> str:
    title = str(item.get("title") or item.get("city_name_ko") or item.get("city_name_en") or "")
    lines = [
        f"이름: {title}",
        f"유형: {_type_label(entity_type)}",
        f"도시: {item.get('city_name_ko') or ''} ({item.get('city_name_en') or ''})",
        f"지역: {item.get('province') or ''}",
    ]
    address = str(item.get("address") or item.get("venue") or "")
    if address:
        lines.append(f"주소: {address}")

    class_tags = _class_tags(item)
    if class_tags:
        lines.append(f"분류: {', '.join(class_tags)}")

    if entity_type == "festival":
        _append(lines, "기간", _date_range(item))
        _append(lines, "장소", item.get("venue"))
        _append(lines, "계절", item.get("season"))
    elif entity_type == "attraction":
        _append(lines, "테마", item.get("theme"))
    else:
        _append(lines, "도시 ID", item.get("city_id"))

    _append(lines, "설명", item.get("description"))
    return "\n".join(line for line in lines if line.strip())


def _normalize_entity_type(entity_type: str) -> str:
    return "city" if entity_type == "city_metadata" else entity_type


def _type_label(entity_type: str) -> str:
    return {
        "city": "도시",
        "attraction": "관광지",
        "festival": "축제",
    }.get(entity_type, entity_type)


def _append(lines: list[str], label: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        lines.append(f"{label}: {value}")


def _date_range(item: dict[str, Any]) -> str:
    start = item.get("eventstartdate") or item.get("event_start_date") or ""
    end = item.get("eventenddate") or item.get("event_end_date") or ""
    return f"{start}~{end}".strip("~")


def _tags(item: dict[str, Any], entity_type: str) -> list[str]:
    tags = _string_values(item.get("theme_tags") or item.get("season_tags") or [])
    theme = item.get("theme")
    if theme:
        tags.append(str(theme))
    tags.extend(_class_tags(item))
    return list(dict.fromkeys(tags))


def _class_tags(item: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("class_tags", "classification_tags", "category_tags", "cuisine_tags"):
        tags.extend(_string_values(item.get(key)))
    classification = item.get("classification")
    if isinstance(classification, dict):
        for key in ("class", "category", "theme", "type", "tags"):
            tags.extend(_string_values(classification.get(key)))
    else:
        tags.extend(_string_values(classification))
    return list(dict.fromkeys(tags))


def _string_values(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_string_values(item))
        return values
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_string_values(item))
        return values
    return [str(value)]


def _number(value: Any) -> float | int | None:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (float, int)):
        return value
    return None


def _sk_source_id(item: dict[str, Any]) -> str:
    sk = str(item.get("SK") or "")
    return sk.split("#", 1)[1] if "#" in sk else sk
