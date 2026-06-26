"""S3 Vector metadata allowlist and size checks."""

from __future__ import annotations

import copy
import json
import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

FILTERABLE_METADATA_KEYS = {
    "country",
    "province",
    "city_id",
    "city_name_en",
    "city_name_ko",
    "entity_type",
    "source_type",
    "source_id",
    "place_id",
    "title",
    "class_tags",
    "theme_tags",
    "season_tags",
    "visit_months",
    "latitude",
    "longitude",
    "attraction_subtype_code",
    "indoor_outdoor",
    "vibe_tags",
    "experience_tags",
    "companion_fit",
    "schema_version",
}

FORBIDDEN_METADATA_KEYS = frozenset({
    "description",
    "overview",
    "opening_hours",
    "closed_days",
    "experience_guide",
    "parking",
    "homepage",
    "image_url",
    "metadata_enrichment",
})
NON_FILTERABLE_METADATA_KEYS = {"raw_s3_uri", "ddb_pk", "ddb_sk", "embedding_model"}
ALLOWED_METADATA_KEYS = FILTERABLE_METADATA_KEYS | NON_FILTERABLE_METADATA_KEYS
FILTERABLE_METADATA_BUDGET_BYTES = 2048


class MetadataValidationError(ValueError):
    """Raised when S3 Vector metadata violates the project contract."""


def validate_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    metadata = {key: _json_safe(value) for key, value in metadata.items()}
    unknown_keys = set(metadata) - ALLOWED_METADATA_KEYS
    if unknown_keys:
        raise MetadataValidationError(f"metadata keys are not allowlisted: {sorted(unknown_keys)}")

    filterable = {key: value for key, value in metadata.items() if key in FILTERABLE_METADATA_KEYS}
    encoded = json.dumps(filterable, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > FILTERABLE_METADATA_BUDGET_BYTES:
        raise MetadataValidationError(
            f"filterable metadata is {len(encoded)} bytes, exceeds {FILTERABLE_METADATA_BUDGET_BYTES}"
        )
    return metadata


ENRICHMENT_DERIVED_KEYS = frozenset({
    "indoor_outdoor",
    "vibe_tags",
    "experience_tags",
    "companion_fit",
    "schema_version",
})


def build_enriched_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """DynamoDB item에서 vector metadata 구성.

    Includes enrichment-derived fields (indoor_outdoor, vibe_tags,
    experience_tags, companion_fit, schema_version)
    only when metadata_enrichment.status == "succeeded".

    Strips None, empty string, and empty array values.
    Excludes all forbidden fields.
    """
    enrichment_obj = item.get("metadata_enrichment")
    enrichment_succeeded = (
        isinstance(enrichment_obj, dict)
        and enrichment_obj.get("status") == "succeeded"
    )

    result: dict[str, Any] = {}
    for key in FILTERABLE_METADATA_KEYS:
        # Skip forbidden fields (should not be in FILTERABLE_METADATA_KEYS, but guard anyway)
        if key in FORBIDDEN_METADATA_KEYS:
            continue

        # Skip enrichment-derived fields unless status == "succeeded"
        if key in ENRICHMENT_DERIVED_KEYS and not enrichment_succeeded:
            continue

        value = item.get(key)

        # Strip None, empty string, and empty array values
        if value is None or value == "" or value == []:
            continue

        result[key] = _json_safe(value)

    return result


def compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe(value) for key, value in metadata.items() if value not in (None, "", [], {})}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def trim_to_budget(
    metadata: dict[str, Any],
    budget: int = 2048,
) -> dict[str, Any] | None:
    """초과 시 배열 필드 뒤에서 trim. 실패 시 None 반환."""
    result = copy.deepcopy(metadata)

    def _filterable_size(meta: dict[str, Any]) -> int:
        filterable = {k: v for k, v in meta.items() if k in FILTERABLE_METADATA_KEYS}
        return len(json.dumps(filterable, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    if _filterable_size(result) <= budget:
        return result

    # Trim experience_tags from the end first
    while result.get("experience_tags") and _filterable_size(result) > budget:
        result["experience_tags"].pop()

    if _filterable_size(result) <= budget:
        return result

    # Then trim vibe_tags from the end
    while result.get("vibe_tags") and _filterable_size(result) > budget:
        result["vibe_tags"].pop()

    if _filterable_size(result) <= budget:
        return result

    # Still exceeds after all trimming
    logger.error(
        "Metadata exceeds %d bytes budget even after trimming array fields: %d bytes",
        budget,
        _filterable_size(result),
    )
    return None
