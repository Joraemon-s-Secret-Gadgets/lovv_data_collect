"""Pipeline stage protocol and canonical stage ordering.

Defines the PipelineStage Protocol that all pipeline stages must implement,
and the canonical stage execution order for the unified preprocessing pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from kr_unified_pipeline.models import PipelineContext


class PipelineStage(Protocol):
    """통합 파이프라인의 개별 실행 단계.

    Each stage receives a PipelineContext, performs its processing,
    and returns an updated PipelineContext with accumulated results.
    """

    @property
    def name(self) -> str:
        """Stage identifier used for logging and configuration."""
        ...

    def execute(self, context: PipelineContext) -> PipelineContext:
        """컨텍스트를 입력받아 갱신된 컨텍스트를 반환한다."""
        ...


# Canonical stage execution order.
# When multiple stages are specified, the orchestrator executes them
# in this defined sequential order regardless of the order provided by the user.
STAGE_ORDER: list[str] = [
    "wikipedia",
    "tourapi-region",
    "tourapi-detail",
    "load",
    "vector-build",
]

# ---------------------------------------------------------------------------
# Stage Wrapper Implementations
# ---------------------------------------------------------------------------

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kr_unified_pipeline.models import CityRecord, PipelineContext, StageResult

logger = logging.getLogger(__name__)


def _load_existing_city_records(output_dir: str) -> list[CityRecord]:
    """Load existing CityRecords from the output directory's cities.json.

    Used when a stage is executed independently so it has a base dataset
    to work with from previous pipeline runs.
    """
    cities_path = Path(output_dir) / "cities.json"
    if not cities_path.exists():
        return []
    try:
        raw_list = json.loads(cities_path.read_text(encoding="utf-8"))
        if not isinstance(raw_list, list):
            return []
        return [CityRecord.from_dict(item) for item in raw_list if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("Could not load existing cities from %s: %s", cities_path, exc)
        return []


def _filter_by_province(records: list[CityRecord], province_id: str | None) -> list[CityRecord]:
    """Filter CityRecords to only those matching the given province_id."""
    if not province_id:
        return records
    return [r for r in records if r.prefecture_id == province_id]


class WikipediaStage:
    """Wikipedia city acquisition stage wrapping crawling.KR.pipeline logic.

    Collects city metadata (description, coordinates, climate) from Korean
    Wikipedia pages and converts results into unified CityRecords.
    """

    @property
    def name(self) -> str:
        return "wikipedia"

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute Wikipedia data acquisition.

        If the crawling.KR.pipeline module is importable, delegates to its
        acquire_city_data function. Otherwise logs a warning and returns
        context unchanged.
        """
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stage_result = StageResult(stage_name=self.name, started_at=started_at)

        # Load existing records if context has none (independent execution)
        if not context.city_records:
            context.city_records = _load_existing_city_records(context.config.output_dir)

        try:
            from crawling.KR.pipeline import acquire_city_data, load_targets
        except (ImportError, SyntaxError, Exception) as import_exc:
            logger.warning(
                "crawling.KR.pipeline is not importable (%s). "
                "WikipediaStage returning context unchanged. "
                "Ensure the crawling package is available in the deployment environment.",
                import_exc,
            )
            stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            context.stage_results.append(stage_result)
            return context

        output_dir = Path(context.config.output_dir)
        province_id = context.config.province_id

        # Determine targets: load from target JSON files for the province
        # or use existing city records to re-fetch Wikipedia data
        targets_dir = Path("crawling/KR/targets")
        page_targets: list[Any] = []

        if targets_dir.exists():
            for target_file in sorted(targets_dir.glob("*_municipalities_ko.json")):
                try:
                    loaded = load_targets(
                        path=target_file,
                        titles=[],
                        default_lang="ko",
                        default_prefecture_id="",
                    )
                    page_targets.extend(loaded)
                except Exception as exc:
                    logger.warning("Failed to load targets from %s: %s", target_file, exc)

        # Filter by province_id if specified
        if province_id and page_targets:
            page_targets = [t for t in page_targets if t.prefecture_id == province_id]

        if not page_targets:
            # Fallback: use existing city record titles
            records_to_process = _filter_by_province(context.city_records, province_id)
            page_targets = [r.city_name_ko for r in records_to_process if r.city_name_ko]

        if not page_targets:
            logger.info("WikipediaStage: No targets to process.")
            stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            context.stage_results.append(stage_result)
            return context

        try:
            _, city_records_raw = acquire_city_data(
                titles=page_targets,
                output_dir=output_dir,
                source_lang="ko",
            )

            # Convert crawling CityRecords to unified pipeline CityRecords
            records_by_id: dict[str, CityRecord] = {r.city_id: r for r in context.city_records}
            records_processed = 0
            records_updated = 0

            for raw_record in city_records_raw:
                unified = CityRecord(
                    city_id=raw_record.city_id,
                    city_name_ko=raw_record.city_name_ko,
                    city_name_ja=getattr(raw_record, "city_name_ja", ""),
                    city_name_en=getattr(raw_record, "city_name_en", ""),
                    prefecture_id=raw_record.prefecture_id,
                    location=getattr(raw_record, "location", ""),
                    latitude=raw_record.latitude,
                    longitude=raw_record.longitude,
                    description=raw_record.description,
                    geography_description=getattr(raw_record, "geography_description", ""),
                    climate_table=getattr(raw_record, "climate_table", None),
                    site_urls=getattr(raw_record, "site_urls", []),
                    source_name=raw_record.source_name,
                    source_url=raw_record.source_url,
                    collected_at=raw_record.collected_at,
                    field_status=getattr(raw_record, "field_status", {}),
                    data_confidence=getattr(raw_record, "data_confidence", "medium"),
                )

                if province_id and unified.prefecture_id != province_id:
                    continue

                records_processed += 1
                if unified.city_id in records_by_id:
                    records_updated += 1
                records_by_id[unified.city_id] = unified

            context.city_records = list(records_by_id.values())
            stage_result.records_processed = records_processed
            stage_result.records_updated = records_updated

        except Exception as exc:
            error_msg = f"WikipediaStage error: {exc}"
            logger.error(error_msg)
            stage_result.errors.append(error_msg)
            context.errors.append(error_msg)

        stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        context.stage_results.append(stage_result)
        return context


class TourAPIRegionStage:
    """TourAPI region detail acquisition stage wrapping tour_api_region_detail_acquisition.py.

    Fetches attractions and festivals from KorService2 endpoints for targeted
    regions (Gangwon, Gyeongbuk) and enriches CityRecords with detail data.
    """

    @property
    def name(self) -> str:
        return "tourapi-region"

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute TourAPI region detail collection.

        If the crawling.KR.tour_api_region_detail_acquisition module is
        importable, delegates to its collect_regions function. Otherwise
        logs a warning and returns context unchanged.
        """
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stage_result = StageResult(stage_name=self.name, started_at=started_at)

        # Load existing records if context has none (independent execution)
        if not context.city_records:
            context.city_records = _load_existing_city_records(context.config.output_dir)

        try:
            from crawling.KR.tour_api_region_detail_acquisition import (
                collect_regions,
                parse_args,
            )
        except (ImportError, SyntaxError, Exception) as import_exc:
            logger.warning(
                "crawling.KR.tour_api_region_detail_acquisition is not importable (%s). "
                "TourAPIRegionStage returning context unchanged. "
                "Ensure the crawling package is available in the deployment environment.",
                import_exc,
            )
            stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            context.stage_results.append(stage_result)
            return context

        output_dir = Path(context.config.output_dir) / "details"
        province_id = context.config.province_id

        # Build CLI args for the existing module
        argv: list[str] = [
            "--output-dir", str(output_dir),
            "--cities-json", str(Path(context.config.output_dir) / "cities.json"),
        ]
        if context.config.force_refresh:
            argv.append("--overwrite")

        try:
            args = parse_args(argv)
            written_paths = collect_regions(args)

            # Read written detail files and enrich context records
            records_by_id: dict[str, CityRecord] = {r.city_id: r for r in context.city_records}
            records_processed = 0
            records_updated = 0

            for detail_path in written_paths:
                if not detail_path.exists():
                    continue
                try:
                    detail_data = json.loads(detail_path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                if not isinstance(detail_data, dict):
                    continue

                meta = detail_data.get("meta", {})
                city_name_ko = meta.get("city_name_ko", "")

                # Find matching CityRecord
                matched_record: CityRecord | None = None
                for record in records_by_id.values():
                    if record.city_name_ko == city_name_ko:
                        matched_record = record
                        break

                if matched_record is None:
                    continue

                # Apply province filter
                if province_id and matched_record.prefecture_id != province_id:
                    continue

                records_processed += 1
                records_updated += 1

            stage_result.records_processed = records_processed
            stage_result.records_updated = records_updated

        except Exception as exc:
            error_msg = f"TourAPIRegionStage error: {exc}"
            logger.error(error_msg)
            stage_result.errors.append(error_msg)
            context.errors.append(error_msg)

        stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        context.stage_results.append(stage_result)
        return context


class TourAPIDetailStage:
    """TourAPI detail harvester stage wrapping tour_api_detail_harvester.py.

    Extracts city-detail payloads from tour-api-korea repository artifacts
    and enriches CityRecords with attraction/festival detail data.
    """

    @property
    def name(self) -> str:
        return "tourapi-detail"

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute TourAPI detail extraction from repository artifacts.

        If the crawling.KR.tour_api_detail_harvester module is importable,
        delegates to its extract_city_details function. Otherwise logs a
        warning and returns context unchanged.
        """
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stage_result = StageResult(stage_name=self.name, started_at=started_at)

        # Load existing records if context has none (independent execution)
        if not context.city_records:
            context.city_records = _load_existing_city_records(context.config.output_dir)

        try:
            from crawling.KR.tour_api_detail_harvester import (
                extract_city_details,
                load_city_targets,
                resolve_repo_path,
                CityTarget,
            )
        except (ImportError, SyntaxError, Exception) as import_exc:
            logger.warning(
                "crawling.KR.tour_api_detail_harvester is not importable (%s). "
                "TourAPIDetailStage returning context unchanged. "
                "Ensure the crawling package is available in the deployment environment.",
                import_exc,
            )
            stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            context.stage_results.append(stage_result)
            return context

        output_dir = Path(context.config.output_dir) / "details"
        cities_json = Path(context.config.output_dir) / "cities.json"
        province_id = context.config.province_id

        try:
            # Load city targets from existing cities.json
            city_targets: list[Any] = []
            if cities_json.exists():
                city_targets = load_city_targets(cities_json)

            # Filter by province_id if specified
            if province_id and city_targets:
                city_targets = [
                    t for t in city_targets
                    if t.prefecture_id == province_id
                ]

            if not city_targets:
                logger.info("TourAPIDetailStage: No city targets to process.")
                stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                context.stage_results.append(stage_result)
                return context

            # Resolve repo path (will clone if not available locally)
            repo_path = resolve_repo_path(
                repo_path=None,
                repo_url="https://github.com/Gloveman/tour-api-korea",
                repo_branch="main",
            )

            results = extract_city_details(
                city_targets=city_targets,
                repo_path=repo_path,
                output_dir=output_dir,
                overwrite=context.config.force_refresh,
            )

            # Update stage metrics
            records_by_id: dict[str, CityRecord] = {r.city_id: r for r in context.city_records}
            records_processed = 0
            records_updated = 0

            for result in results:
                if not isinstance(result, dict):
                    continue
                meta = result.get("meta", {})
                city_id = meta.get("city_id", "")

                if city_id and city_id in records_by_id:
                    records_processed += 1
                    records_updated += 1

            stage_result.records_processed = records_processed
            stage_result.records_updated = records_updated

        except Exception as exc:
            error_msg = f"TourAPIDetailStage error: {exc}"
            logger.error(error_msg)
            stage_result.errors.append(error_msg)
            context.errors.append(error_msg)

        stage_result.completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        context.stage_results.append(stage_result)
        return context
