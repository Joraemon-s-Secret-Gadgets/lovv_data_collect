"""
Incremental merge logic for the unified preprocessing pipeline.

Loads existing cities.json as a base dataset, merges newly processed
CityRecords with confidence-based field precedence, preserves all
existing records, and writes the result atomically.

Implements Requirements 9.1, 9.2, 9.3, 9.4, 9.5.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from kr_unified_pipeline.models import CityRecord, ImageSource

logger = logging.getLogger(__name__)

# Confidence hierarchy: higher index = higher confidence
_CONFIDENCE_LEVELS: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def _confidence_rank(level: str) -> int:
    """Return numeric rank for a confidence level string.

    Unknown levels are treated as 0 (lowest).
    """
    return _CONFIDENCE_LEVELS.get(level, 0)


def _is_empty(value: object) -> bool:
    """Check if a value is considered empty/missing.

    Empty means None, empty string, or whitespace-only string.
    """
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


# Fields eligible for confidence-based merge (excludes identity/key fields
# and special fields handled separately like image_url/image_urls).
_MERGEABLE_FIELDS: tuple[str, ...] = (
    "city_name_ko",
    "city_name_ja",
    "city_name_en",
    "prefecture_id",
    "location",
    "latitude",
    "longitude",
    "description",
    "geography_description",
    "climate_table",
    "site_urls",
    "source_name",
    "source_url",
    "collected_at",
    "verified_at",
    "verified_source_url",
    "verification_note",
)


def load_base_dataset(cities_json_path: Path) -> dict[str, CityRecord]:
    """Load existing cities.json as the base dataset for incremental merge.

    If the file does not exist or cannot be parsed, returns an empty dict
    (Requirement 9.1, graceful handling of missing file).

    Args:
        cities_json_path: Path to the cities.json file.

    Returns:
        A dict mapping city_id to CityRecord.
    """
    if not cities_json_path.exists():
        logger.info("No existing cities.json found at %s; starting with empty base.", cities_json_path)
        return {}

    try:
        raw_text = cities_json_path.read_text(encoding="utf-8")
        raw_list = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load cities.json at %s: %s. Starting with empty base.", cities_json_path, exc)
        return {}

    if not isinstance(raw_list, list):
        logger.warning("cities.json at %s is not a JSON array. Starting with empty base.", cities_json_path)
        return {}

    base: dict[str, CityRecord] = {}
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        record = CityRecord.from_dict(item)
        if record.city_id:
            base[record.city_id] = record

    logger.info("Loaded %d records from base dataset %s.", len(base), cities_json_path)
    return base


def merge_records(
    base: dict[str, CityRecord],
    incoming: list[CityRecord],
    *,
    force_image_update: bool = False,
) -> dict[str, CityRecord]:
    """Merge incoming CityRecords into the base dataset.

    Merge rules (Requirements 9.2, 9.3, 9.4, 9.5):
    - Only update fields when the incoming record has equal or higher
      data_confidence; never overwrite valid data with empty/lower-confidence values.
    - Record previous and new value sources in field_status for auditability.
    - Preserve all base records even if not in incoming list.
    - Image merge: without force_image_update, append new URL to image_urls
      and keep existing image_url as primary. With force_image_update, replace
      image_url with new URL.

    Args:
        base: The existing dataset keyed by city_id.
        incoming: List of newly processed CityRecords.
        force_image_update: If True, replace image_url with the new value.

    Returns:
        The merged dataset keyed by city_id (base is also mutated in place).
    """
    for new_record in incoming:
        if not new_record.city_id:
            continue

        if new_record.city_id not in base:
            # New record not in base — add directly
            base[new_record.city_id] = new_record
            continue

        existing = base[new_record.city_id]
        _merge_single_record(existing, new_record, force_image_update=force_image_update)

    return base


def _merge_single_record(
    existing: CityRecord,
    incoming: CityRecord,
    *,
    force_image_update: bool = False,
) -> None:
    """Merge a single incoming record into an existing record in place.

    Requirement 9.2: Update only fields with equal or higher data_confidence.
    Requirement 9.3: Record previous/new value source in field_status.
    Requirement 9.5: Handle image merge rules.
    """
    existing_rank = _confidence_rank(existing.data_confidence)
    incoming_rank = _confidence_rank(incoming.data_confidence)

    # Requirement 9.2: Only merge if incoming confidence is >= existing
    if incoming_rank >= existing_rank:
        _merge_fields(existing, incoming)

    # Always merge images regardless of confidence (images are additive)
    _merge_images(existing, incoming, force_image_update=force_image_update)

    # Update data_confidence to the higher value
    if incoming_rank > existing_rank:
        existing.data_confidence = incoming.data_confidence


def _merge_fields(existing: CityRecord, incoming: CityRecord) -> None:
    """Merge individual fields from incoming into existing.

    Only overwrites a field if the incoming value is non-empty.
    Records the source change in field_status for auditability (Requirement 9.3).
    """
    for field_name in _MERGEABLE_FIELDS:
        incoming_value = getattr(incoming, field_name, None)
        existing_value = getattr(existing, field_name, None)

        # Never overwrite valid data with empty values
        if _is_empty(incoming_value):
            continue

        # If existing value is empty, always accept the incoming value
        if _is_empty(existing_value):
            setattr(existing, field_name, incoming_value)
            # Record in field_status for auditability (Requirement 9.3)
            existing.field_status[field_name] = (
                f"updated: source={incoming.source_name or 'unknown'}"
            )
            continue

        # Both have values — update only if values differ
        if existing_value != incoming_value:
            prev_source = existing.source_name or "unknown"
            new_source = incoming.source_name or "unknown"
            setattr(existing, field_name, incoming_value)
            # Requirement 9.3: Record previous and new source
            existing.field_status[field_name] = (
                f"merged: prev_source={prev_source}, new_source={new_source}"
            )


def _merge_images(
    existing: CityRecord,
    incoming: CityRecord,
    *,
    force_image_update: bool = False,
) -> None:
    """Merge image fields between existing and incoming records.

    Requirement 9.5:
    - Without force_image_update: append new URL to image_urls and keep
      existing image_url as primary.
    - With force_image_update: replace image_url with new URL.
    """
    new_image_url = incoming.image_url

    if not new_image_url:
        # No new image to merge; still merge image_urls list
        _merge_image_urls_list(existing, incoming)
        return

    if existing.image_url is None:
        # No existing primary image — accept new one directly
        existing.image_url = new_image_url
        existing.field_status["image_url"] = (
            f"updated: source={incoming.source_name or 'unknown'}"
        )
    elif new_image_url != existing.image_url:
        if force_image_update:
            # Requirement 9.5: With --force-image-update, replace
            prev_source = existing.source_name or "unknown"
            new_source = incoming.source_name or "unknown"
            existing.image_url = new_image_url
            existing.field_status["image_url"] = (
                f"force_replaced: prev_source={prev_source}, new_source={new_source}"
            )
        else:
            # Requirement 9.5: Without force, append to image_urls, keep existing primary
            _append_image_url(existing, new_image_url, incoming.source_name or "unknown")

    # Merge the image_urls lists
    _merge_image_urls_list(existing, incoming)


def _merge_image_urls_list(existing: CityRecord, incoming: CityRecord) -> None:
    """Merge incoming image_urls into existing, avoiding duplicates."""
    existing_urls = {img.url for img in existing.image_urls}
    for img_source in incoming.image_urls:
        if img_source.url not in existing_urls:
            existing.image_urls.append(img_source)
            existing_urls.add(img_source.url)


def _append_image_url(existing: CityRecord, url: str, source: str) -> None:
    """Append a URL to the existing record's image_urls if not already present."""
    if not any(img.url == url for img in existing.image_urls):
        existing.image_urls.append(ImageSource(url=url, source=source))


def save_dataset(
    dataset: dict[str, CityRecord],
    cities_json_path: Path,
) -> None:
    """Write the merged dataset to cities.json atomically.

    Uses a temporary file + rename to avoid partial writes on failure.

    Args:
        dataset: The merged city records keyed by city_id.
        cities_json_path: Path to the output cities.json file.
    """
    records_list = [record.to_dict() for record in dataset.values()]
    json_content = json.dumps(records_list, ensure_ascii=False, indent=2)

    # Ensure parent directory exists
    cities_json_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to temp file in same directory, then rename
    dir_path = cities_json_path.parent
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix="cities_",
            dir=str(dir_path),
        )
        os.write(fd, json_content.encode("utf-8"))
        os.close(fd)
        fd = None

        # On Windows, os.replace handles atomic replacement
        os.replace(tmp_path, str(cities_json_path))
        tmp_path = None
        logger.info("Saved %d records to %s.", len(records_list), cities_json_path)
    except Exception:
        if fd is not None:
            os.close(fd)
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def incremental_merge(
    cities_json_path: Path,
    incoming_records: list[CityRecord],
    *,
    force_image_update: bool = False,
) -> dict[str, CityRecord]:
    """Perform a full incremental merge cycle: load → merge → save.

    This is the primary entry point for the merge module.

    Args:
        cities_json_path: Path to the cities.json file (base and output).
        incoming_records: Newly processed CityRecords to merge.
        force_image_update: If True, replace existing image_url with new one.

    Returns:
        The final merged dataset keyed by city_id.
    """
    base = load_base_dataset(cities_json_path)
    merged = merge_records(base, incoming_records, force_image_update=force_image_update)
    save_dataset(merged, cities_json_path)
    return merged
