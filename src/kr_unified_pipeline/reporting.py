"""
Pipeline execution reporting module.

Provides structured report generation for the unified preprocessing pipeline.
Supports multiple output formats: console display, JSON file, and Lambda response
dictionary. Includes verbose mode for per-record processing details.

Implements Requirements 8.1, 8.2, 8.3, 8.4, 8.5.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kr_unified_pipeline.models import (
    PipelineContext,
    ReviewEntry,
    StageResult,
)

logger = logging.getLogger(__name__)


def generate_report(context: PipelineContext, verbose: bool = False) -> dict[str, Any]:
    """Create a structured report dictionary from pipeline execution context.

    Requirement 8.1: Total records processed, records per stage, review
                     transitions, images collected.
    Requirement 8.2: Start and completion timestamp of each stage.
    Requirement 8.3: Count of records per review_reason category.
    Requirement 8.4: API errors, network failures, parsing errors with city_id.
    Requirement 8.5: Verbose per-record processing details.

    Args:
        context: The final PipelineContext after pipeline execution.
        verbose: If True, include per-record details (field_status changes,
                 image resolution results).

    Returns:
        Structured dictionary suitable for JSON serialization, console
        formatting, or Lambda response payload.
    """
    # Requirement 8.1: Summary metrics
    total_records = len(context.city_records)
    total_images = sum(sr.images_collected for sr in context.stage_results)
    total_review = len(context.review_manifest)

    # Requirement 8.2: Per-stage timing and metrics
    stages: list[dict[str, Any]] = []
    for sr in context.stage_results:
        stages.append(_build_stage_entry(sr))

    # Requirement 8.3: Review reason counts
    review_reason_counts = _count_review_reasons(context.review_manifest)

    # Requirement 8.4: Categorized errors
    error_details = _categorize_errors(context)

    report: dict[str, Any] = {
        "pipeline_start_time": context.start_time,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_records_processed": total_records,
            "total_images_collected": total_images,
            "records_transitioned_to_review": total_review,
            "total_errors": len(context.errors),
        },
        "stages": stages,
        "review_reason_counts": review_reason_counts,
        "errors": error_details,
    }

    # Requirement 8.5: Verbose per-record details
    if verbose:
        report["record_details"] = _build_record_details(context)

    return report


def format_console_report(report: dict[str, Any]) -> str:
    """Format a structured report dictionary for console/CLI output.

    Produces a human-readable text summary suitable for terminal display.

    Args:
        report: Report dictionary from generate_report().

    Returns:
        Multi-line formatted string for console output.
    """
    lines: list[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append("PIPELINE EXECUTION REPORT")
    lines.append(sep)
    lines.append("")

    # Timing
    lines.append(f"Pipeline start: {report.get('pipeline_start_time', 'N/A')}")
    lines.append(f"Report generated: {report.get('report_generated_at', 'N/A')}")
    lines.append("")

    # Summary
    summary = report.get("summary", {})
    lines.append("Summary:")
    lines.append(f"  Total records processed: {summary.get('total_records_processed', 0)}")
    lines.append(f"  Total images collected: {summary.get('total_images_collected', 0)}")
    lines.append(
        f"  Records transitioned to review: {summary.get('records_transitioned_to_review', 0)}"
    )
    lines.append(f"  Total errors: {summary.get('total_errors', 0)}")
    lines.append("")

    # Per-stage results (Requirement 8.2)
    stages = report.get("stages", [])
    if stages:
        lines.append("Stage Results:")
        for stage in stages:
            lines.append(f"  [{stage.get('stage_name', '?')}]")
            lines.append(f"    Started:  {stage.get('started_at', 'N/A')}")
            lines.append(f"    Completed: {stage.get('completed_at', 'N/A')}")
            lines.append(f"    Records processed: {stage.get('records_processed', 0)}")
            lines.append(f"    Records updated: {stage.get('records_updated', 0)}")
            lines.append(f"    Images collected: {stage.get('images_collected', 0)}")
            stage_errors = stage.get("errors", [])
            if stage_errors:
                lines.append(f"    Errors: {len(stage_errors)}")
        lines.append("")

    # Review reason counts (Requirement 8.3)
    review_counts = report.get("review_reason_counts", {})
    if review_counts:
        lines.append("Review Reasons:")
        for reason, count in sorted(review_counts.items()):
            lines.append(f"  {reason}: {count}")
        lines.append("")

    # Errors (Requirement 8.4)
    error_details = report.get("errors", {})
    api_errors = error_details.get("api_errors", [])
    network_errors = error_details.get("network_errors", [])
    parsing_errors = error_details.get("parsing_errors", [])
    other_errors = error_details.get("other_errors", [])

    has_errors = api_errors or network_errors or parsing_errors or other_errors
    if has_errors:
        lines.append("Errors:")
        if api_errors:
            lines.append(f"  API errors ({len(api_errors)}):")
            for err in api_errors:
                lines.append(f"    - {err}")
        if network_errors:
            lines.append(f"  Network failures ({len(network_errors)}):")
            for err in network_errors:
                lines.append(f"    - {err}")
        if parsing_errors:
            lines.append(f"  Parsing errors ({len(parsing_errors)}):")
            for err in parsing_errors:
                lines.append(f"    - {err}")
        if other_errors:
            lines.append(f"  Other errors ({len(other_errors)}):")
            for err in other_errors:
                lines.append(f"    - {err}")
        lines.append("")

    # Verbose: per-record details (Requirement 8.5)
    record_details = report.get("record_details")
    if record_details:
        lines.append("Per-Record Details:")
        for rec in record_details:
            city_id = rec.get("city_id", "?")
            city_name = rec.get("city_name_ko", "")
            confidence = rec.get("data_confidence", "?")
            image_url = rec.get("image_url") or "none"
            field_status = rec.get("field_status", {})
            status_str = ", ".join(f"{k}={v}" for k, v in field_status.items()) if field_status else "all ok"
            lines.append(f"  {city_id} ({city_name}): confidence={confidence}, image={image_url}, status=[{status_str}]")
        lines.append("")

    lines.append(sep)
    return "\n".join(lines)


def write_report_file(report: dict[str, Any], output_dir: Path) -> Path:
    """Write the report as a JSON file to the specified output directory.

    The file is named with the current UTC timestamp for traceability.

    Args:
        report: Report dictionary from generate_report().
        output_dir: Directory where the report file will be written.

    Returns:
        Path to the written report file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"pipeline_report_{timestamp}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Report written to %s", filepath)
    return filepath


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_stage_entry(sr: StageResult) -> dict[str, Any]:
    """Build a report entry for a single stage result.

    Requirement 8.2: Start and completion timestamps of each stage.
    """
    return {
        "stage_name": sr.stage_name,
        "started_at": sr.started_at,
        "completed_at": sr.completed_at,
        "records_processed": sr.records_processed,
        "records_updated": sr.records_updated,
        "images_collected": sr.images_collected,
        "errors": sr.errors,
    }


def _count_review_reasons(review_manifest: list[ReviewEntry]) -> dict[str, int]:
    """Count records per review_reason category.

    Requirement 8.3: Count of records per review_reason category.
    """
    counts: dict[str, int] = {}
    for entry in review_manifest:
        reason = entry.review_reason
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _categorize_errors(context: PipelineContext) -> dict[str, list[str]]:
    """Categorize errors into API, network, parsing, and other.

    Requirement 8.4: Log API errors, network failures, parsing errors
                     with affected city_id.

    Heuristic classification based on error message content:
    - API errors: contain "api", "status", "401", "403", "429", "500"
    - Network errors: contain "network", "timeout", "connection", "socket"
    - Parsing errors: contain "parse", "json", "decode", "key", "format"
    - Other: everything else
    """
    api_errors: list[str] = []
    network_errors: list[str] = []
    parsing_errors: list[str] = []
    other_errors: list[str] = []

    all_errors = list(context.errors)
    # Also include per-stage errors
    for sr in context.stage_results:
        all_errors.extend(sr.errors)

    for error in all_errors:
        lower = error.lower()
        if any(kw in lower for kw in ("api", "status code", "401", "403", "429", "500", "502", "503")):
            api_errors.append(error)
        elif any(kw in lower for kw in ("network", "timeout", "connection", "socket", "dns", "unreachable")):
            network_errors.append(error)
        elif any(kw in lower for kw in ("parse", "json", "decode", "keyerror", "format", "invalid syntax")):
            parsing_errors.append(error)
        else:
            other_errors.append(error)

    return {
        "api_errors": api_errors,
        "network_errors": network_errors,
        "parsing_errors": parsing_errors,
        "other_errors": other_errors,
    }


def _build_record_details(context: PipelineContext) -> list[dict[str, Any]]:
    """Build per-record processing details for verbose mode.

    Requirement 8.5: Per-record processing details including field_status
                     changes and image resolution results.
    """
    details: list[dict[str, Any]] = []
    for record in context.city_records:
        entry: dict[str, Any] = {
            "city_id": record.city_id,
            "city_name_ko": record.city_name_ko,
            "prefecture_id": record.prefecture_id,
            "data_confidence": record.data_confidence,
            "image_url": record.image_url,
            "image_sources": [
                {"url": img.url, "source": img.source} for img in record.image_urls
            ],
            "field_status": dict(record.field_status),
        }
        details.append(entry)
    return details
