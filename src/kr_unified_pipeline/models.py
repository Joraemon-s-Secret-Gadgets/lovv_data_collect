"""
Core data models for the unified preprocessing pipeline.

This module defines all dataclasses used across the pipeline including
CityRecord (extended with image fields), pipeline context, configuration,
completeness evaluation results, review entries, stage results, and
rebuild/test summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Image Source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageSource:
    """An image URL with its origin attribution.

    Attributes:
        url: The HTTP/HTTPS URL of the image.
        source: Origin identifier, e.g. "wikipedia" or "tourapi".
    """

    url: str
    source: str  # "wikipedia" | "tourapi"


# ---------------------------------------------------------------------------
# Extended CityRecord (with image fields)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CityRecord:
    """City metadata record extended with image URL fields.

    Extends the conceptual NormalizedRecord with all city-specific fields
    and image support for the unified pipeline. Supports JSON serialization
    with backward compatibility for missing image fields.

    Attributes:
        city_id: Unique city identifier.
        city_name_ko: Korean name of the city.
        city_name_ja: Japanese name of the city.
        city_name_en: English name of the city.
        prefecture_id: Parent province/prefecture identifier.
        location: Human-readable location description.
        latitude: Geographic latitude (None if unknown).
        longitude: Geographic longitude (None if unknown).
        description: City description text.
        geography_description: Geographic characteristics.
        climate_table: Monthly climate data mapping.
        site_urls: List of related website URLs.
        image_url: Primary representative image URL (None if unavailable).
        image_urls: All collected image URLs with source attribution.
        source_name: Data source name.
        source_url: Data source URL.
        collected_at: ISO 8601 timestamp of collection.
        field_status: Per-field status tracking dict.
        data_confidence: Confidence level: "high", "medium", or "low".
        verified_at: ISO 8601 timestamp of verification (if any).
        verified_source_url: URL used for verification.
        verification_note: Note about verification result.
    """

    # City-specific fields
    city_id: str = ""
    city_name_ko: str = ""
    city_name_ja: str = ""
    city_name_en: str = ""
    prefecture_id: str = ""
    location: str = ""
    latitude: float | None = None
    longitude: float | None = None
    description: str = ""
    geography_description: str = ""
    climate_table: dict[str, str] | None = None
    site_urls: list[str] = field(default_factory=list)

    # Image fields (Requirement 7.1, 7.2, 7.4)
    image_url: str | None = None
    image_urls: list[ImageSource] = field(default_factory=list)

    # NormalizedRecord fields
    source_name: str = ""
    source_url: str = ""
    collected_at: str = ""
    field_status: dict[str, str] = field(default_factory=dict)
    data_confidence: str = "medium"
    verified_at: str | None = None
    verified_source_url: str | None = None
    verification_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary.

        Image fields are always included for forward compatibility.
        ImageSource entries are serialized as {"url": ..., "source": ...}.
        """
        return {
            "city_id": self.city_id,
            "city_name_ko": self.city_name_ko,
            "city_name_ja": self.city_name_ja,
            "city_name_en": self.city_name_en,
            "prefecture_id": self.prefecture_id,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "description": self.description,
            "geography_description": self.geography_description,
            "climate_table": self.climate_table,
            "site_urls": self.site_urls,
            "image_url": self.image_url,
            "image_urls": [{"url": img.url, "source": img.source} for img in self.image_urls],
            "source_name": self.source_name,
            "source_url": self.source_url,
            "collected_at": self.collected_at,
            "field_status": self.field_status,
            "data_confidence": self.data_confidence,
            "verified_at": self.verified_at,
            "verified_source_url": self.verified_source_url,
            "verification_note": self.verification_note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CityRecord:
        """Deserialize from a JSON-compatible dictionary.

        Handles backward compatibility: missing image_url defaults to None,
        missing image_urls defaults to empty list (Requirement 7.5).
        """
        image_urls_raw = data.get("image_urls", [])
        image_urls = [
            ImageSource(url=entry["url"], source=entry["source"])
            for entry in image_urls_raw
            if isinstance(entry, dict) and "url" in entry and "source" in entry
        ]

        return cls(
            city_id=data.get("city_id", ""),
            city_name_ko=data.get("city_name_ko", ""),
            city_name_ja=data.get("city_name_ja", ""),
            city_name_en=data.get("city_name_en", ""),
            prefecture_id=data.get("prefecture_id", ""),
            location=data.get("location", ""),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            description=data.get("description", ""),
            geography_description=data.get("geography_description", ""),
            climate_table=data.get("climate_table"),
            site_urls=data.get("site_urls", []),
            image_url=data.get("image_url"),
            image_urls=image_urls,
            source_name=data.get("source_name", ""),
            source_url=data.get("source_url", ""),
            collected_at=data.get("collected_at", ""),
            field_status=data.get("field_status", {}),
            data_confidence=data.get("data_confidence", "medium"),
            verified_at=data.get("verified_at"),
            verified_source_url=data.get("verified_source_url"),
            verification_note=data.get("verification_note"),
        )


# ---------------------------------------------------------------------------
# Pipeline Configuration
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PipelineConfig:
    """Configuration for a unified pipeline run, mapped from CLI options.

    Attributes:
        output_dir: Directory for JSON output files.
        stages: List of stages to execute (empty = all).
        province_id: Limit processing to this province (None = all).
        force_refresh: Re-collect data for already-collected records.
        skip_images: Disable image URL resolution.
        force_image_update: Replace existing image_url with new one.
        verbose: Enable per-record processing details.
        local_test: Activate local test mode.
        bucket: S3 pipeline bucket name.
        ingest_date: Target ingest date partition.
        table_name: DynamoDB table name.
        rebuild_mode: Vector rebuild mode ("full" or "incremental").
        profile: AWS CLI profile name.
        region: AWS region.
    """

    output_dir: str = "data/KR/"
    stages: list[str] = field(default_factory=list)
    province_id: str | None = None
    force_refresh: bool = False
    skip_images: bool = False
    force_image_update: bool = False
    verbose: bool = False
    local_test: bool = False
    bucket: str = ""
    ingest_date: str = ""
    table_name: str = "TourKoreaDomainDataV2"
    rebuild_mode: str = "full"
    profile: str | None = None
    region: str | None = None


# ---------------------------------------------------------------------------
# Stage Result
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StageResult:
    """Result summary for a single pipeline stage execution.

    Attributes:
        stage_name: Name of the executed stage.
        started_at: ISO 8601 timestamp when stage started.
        completed_at: ISO 8601 timestamp when stage completed (empty if still running).
        records_processed: Number of records processed.
        records_updated: Number of records updated with new data.
        errors: List of error messages encountered.
        images_collected: Number of image URLs collected.
    """

    stage_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    records_processed: int = 0
    records_updated: int = 0
    errors: list[str] = field(default_factory=list)
    images_collected: int = 0


# ---------------------------------------------------------------------------
# Pipeline Context
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PipelineContext:
    """Shared state passed between pipeline stages.

    Attributes:
        city_records: Current collection of city records being processed.
        stage_results: Results from each completed stage.
        errors: Global error list across all stages.
        config: Pipeline configuration for this run.
        start_time: ISO 8601 timestamp when pipeline execution began.
        review_manifest: List of records flagged for manual review.
    """

    city_records: list[CityRecord] = field(default_factory=list)
    stage_results: list[StageResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    config: PipelineConfig = field(default_factory=PipelineConfig)
    start_time: str = ""
    review_manifest: list[ReviewEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Completeness Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletenessResult:
    """Result of evaluating a CityRecord's data completeness.

    Attributes:
        data_confidence: Confidence level: "high", "medium", or "low".
        missing_fields: List of field names that are missing or invalid.
        field_statuses: Per-field status mapping (field_name -> status string).
        needs_review: Whether this record requires manual review.
        review_reasons: List of reasons the record was flagged.
    """

    data_confidence: str
    missing_fields: tuple[str, ...] = ()
    field_statuses: dict[str, str] = field(default_factory=dict)
    needs_review: bool = False
    review_reasons: tuple[str, ...] = ()

    def __hash__(self) -> int:
        return hash((
            self.data_confidence,
            self.missing_fields,
            tuple(sorted(self.field_statuses.items())),
            self.needs_review,
            self.review_reasons,
        ))


# ---------------------------------------------------------------------------
# Review Entry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ReviewEntry:
    """An entry in the review manifest for a record needing attention.

    Attributes:
        city_id: The city identifier.
        city_name_ko: Korean name of the city.
        prefecture_id: Parent province/prefecture identifier.
        missing_fields: List of fields that are missing or invalid.
        review_reason: Primary reason for flagging.
        flagged_at: ISO 8601 timestamp when the record was flagged.
    """

    city_id: str = ""
    city_name_ko: str = ""
    prefecture_id: str = ""
    missing_fields: list[str] = field(default_factory=list)
    review_reason: str = ""
    flagged_at: str = ""


# ---------------------------------------------------------------------------
# Rebuild Manifest
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RebuildManifest:
    """Manifest recording a vector index rebuild execution.

    Attributes:
        rebuild_mode: "full" or "incremental".
        start_timestamp: ISO 8601 timestamp when rebuild started.
        end_timestamp: ISO 8601 timestamp when rebuild completed.
        total_items_processed: Total items exported from DynamoDB.
        items_upserted: Items successfully upserted to vector index.
        items_skipped: Items skipped due to errors.
        errors_encountered: List of error messages.
    """

    rebuild_mode: str = "full"
    start_timestamp: str = ""
    end_timestamp: str = ""
    total_items_processed: int = 0
    items_upserted: int = 0
    items_skipped: int = 0
    errors_encountered: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Local Test Summary
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LocalTestSummary:
    """Summary of a local test mode execution for a single province.

    Attributes:
        province_id: The province identifier used for scoping.
        items_read_from_s3: Number of items read from S3.
        items_loaded_to_dynamodb: Number of items loaded to DynamoDB.
        vectors_built: Number of vectors successfully built.
        verdict: "PASS" or "FAIL".
        failed_items: List of identifiers for items that failed.
        execution_time_seconds: Total execution time in seconds.
    """

    province_id: str = ""
    items_read_from_s3: int = 0
    items_loaded_to_dynamodb: int = 0
    vectors_built: int = 0
    verdict: str = "PASS"
    failed_items: list[str] = field(default_factory=list)
    execution_time_seconds: float = 0.0
