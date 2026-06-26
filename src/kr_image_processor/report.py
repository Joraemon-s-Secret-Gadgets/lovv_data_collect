"""Execution report generation for the KR data pipeline.

Aggregates per-city image processing results and stage outcomes into a
comprehensive pipeline execution report, then writes it to S3.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def generate_report(
    s3_client: Any,
    bucket: str,
    ingest_date: str,
    execution_context: dict[str, Any],
) -> dict[str, Any]:
    """Generate and write a pipeline execution report to S3.

    Parameters
    ----------
    s3_client : boto3 S3 client
        Client for the pipeline data bucket.
    bucket : str
        Pipeline data bucket name.
    ingest_date : str
        Ingest date in YYYYMMDD format.
    execution_context : dict
        Contains:
        - image_results: list[dict] — per-city image processing results
        - load_results: dict | None — load stage output
        - vector_results: dict | None — vector stage output
        - start_time: str (ISO 8601) — pipeline start time
        - failure_info: dict | None — failure details if pipeline failed

    Returns
    -------
    dict
        The complete report dict.
    """
    image_results = execution_context.get("image_results", [])
    load_results = execution_context.get("load_results") or {}
    vector_results = execution_context.get("vector_results") or {}
    start_time = execution_context.get("start_time", "")
    failure_info = execution_context.get("failure_info")

    # Aggregate per-city stats
    total_cities = len(image_results)
    total_downloaded = 0
    total_failed = 0
    total_review = 0
    per_city: list[dict[str, Any]] = []

    for city_result in image_results:
        city_name = city_result.get("city_name_en", "unknown")
        downloaded = city_result.get("images_downloaded", 0)
        failed = city_result.get("images_failed", 0)
        no_source = city_result.get("no_source_image", 0)
        review_count = city_result.get("review_count", 0)

        total_downloaded += downloaded
        total_failed += failed
        total_review += review_count

        per_city.append({
            "city_name_en": city_name,
            "images_ok": downloaded,
            "images_failed": failed + no_source,
            "records_loaded": city_result.get("total_records", 0),
        })

    # Extract load/vector stats
    records_loaded = load_results.get("loaded", 0)
    vectors_built = vector_results.get("manifest", {}).get("upserted", 0) if isinstance(vector_results.get("manifest"), dict) else 0

    # Calculate execution time
    completed_at = datetime.now(timezone.utc).isoformat()
    total_execution_time_seconds = 0
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.now(timezone.utc)
            total_execution_time_seconds = int((end_dt - start_dt).total_seconds())
        except (ValueError, TypeError):
            pass

    # Determine status
    if failure_info:
        status = "failed"
    elif total_failed > 0 or total_review > 0:
        status = "partial"
    else:
        status = "success"

    report: dict[str, Any] = {
        "ingest_date": ingest_date,
        "status": status,
        "started_at": start_time,
        "completed_at": completed_at,
        "total_execution_time_seconds": total_execution_time_seconds,
        "summary": {
            "total_cities": total_cities,
            "images_downloaded": total_downloaded,
            "images_failed": total_failed,
            "review_count": total_review,
            "records_loaded": records_loaded,
            "vectors_built": vectors_built,
        },
        "per_city": per_city,
        "failure_info": failure_info,
    }

    # Write report to S3
    report_key = f"processed/KR/reports/{ingest_date}/pipeline_report.json"
    report_body = json.dumps(report, ensure_ascii=False)

    s3_client.put_object(
        Bucket=bucket,
        Key=report_key,
        Body=report_body.encode("utf-8"),
        ContentType="application/json",
    )

    logger.info("Pipeline report written: %s", report_key)

    return report
