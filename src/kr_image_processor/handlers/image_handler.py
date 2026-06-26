"""Multi-command Lambda entry point for kr-pipeline-image.

Routes incoming events to the appropriate processing function based on the
``command`` field in the event payload.

Commands:
  - "process_city" (default): City-level image download and S3 upload.
  - "aggregate_review": Merge per-city review entries into a single manifest.
  - "generate_report": Generate pipeline execution report.
"""

from __future__ import annotations

import logging
import os
import traceback
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point — routes by event["command"].

    Parameters
    ----------
    event : dict
        Lambda event payload. Must contain ``command`` (or defaults to
        ``"process_city"``). Additional keys depend on the command.
    context : Any
        Lambda context object.

    Returns
    -------
    dict
        Response with ``statusCode`` and command-specific result fields.
    """
    command = event.get("command", "process_city")

    try:
        if command == "process_city":
            return _handle_process_city(event)
        elif command == "aggregate_review":
            return _handle_aggregate_review(event)
        elif command == "generate_report":
            return _handle_generate_report(event)
        else:
            return {
                "statusCode": 400,
                "error": f"Unknown command: {command}",
            }
    except Exception as exc:
        logger.error("Handler error [command=%s]: %s", command, exc)
        logger.error(traceback.format_exc())
        return {
            "statusCode": 500,
            "error": str(exc),
            "command": command,
        }


def _get_s3_client():
    """Create and return a boto3 S3 client."""
    import boto3
    return boto3.client("s3")


def _handle_process_city(event: dict[str, Any]) -> dict[str, Any]:
    """Handle the process_city command."""
    from kr_image_processor.processor import process_city

    bucket = event.get("bucket") or os.environ.get("PIPELINE_BUCKET", "")
    image_bucket = event.get("image_bucket") or os.environ.get("IMAGE_BUCKET", "")
    ingest_date = event.get("ingest_date", "")
    city_name_en = event.get("city_name_en", "")
    source_key = event.get("source_key", "")

    if not bucket:
        return {"statusCode": 400, "error": "Missing required parameter: bucket"}
    if not image_bucket:
        return {"statusCode": 400, "error": "Missing required parameter: image_bucket"}
    if not ingest_date:
        return {"statusCode": 400, "error": "Missing required parameter: ingest_date"}
    if not city_name_en:
        return {"statusCode": 400, "error": "Missing required parameter: city_name_en"}
    if not source_key:
        return {"statusCode": 400, "error": "Missing required parameter: source_key"}

    s3_client = _get_s3_client()

    result = process_city(
        s3_client=s3_client,
        image_s3_client=s3_client,
        bucket=bucket,
        image_bucket=image_bucket,
        ingest_date=ingest_date,
        city_name_en=city_name_en,
        source_key=source_key,
    )

    return {
        "statusCode": 200,
        "city_name_en": city_name_en,
        "output_key": f"processed/KR/details/{ingest_date}/images/{city_name_en}.json",
        **result,
    }


def _handle_aggregate_review(event: dict[str, Any]) -> dict[str, Any]:
    """Handle the aggregate_review command."""
    from kr_image_processor.review import aggregate_review

    bucket = event.get("bucket") or os.environ.get("PIPELINE_BUCKET", "")
    ingest_date = event.get("ingest_date", "")
    image_results = event.get("image_results", [])

    if not bucket:
        return {"statusCode": 400, "error": "Missing required parameter: bucket"}
    if not ingest_date:
        return {"statusCode": 400, "error": "Missing required parameter: ingest_date"}

    s3_client = _get_s3_client()

    result = aggregate_review(
        s3_client=s3_client,
        bucket=bucket,
        ingest_date=ingest_date,
        image_results=image_results,
    )

    return {
        "statusCode": 200,
        **result,
    }


def _handle_generate_report(event: dict[str, Any]) -> dict[str, Any]:
    """Handle the generate_report command."""
    from kr_image_processor.report import generate_report

    bucket = event.get("bucket") or os.environ.get("PIPELINE_BUCKET", "")
    ingest_date = event.get("ingest_date", "")
    execution_context = event.get("execution_context", {})

    if not bucket:
        return {"statusCode": 400, "error": "Missing required parameter: bucket"}
    if not ingest_date:
        return {"statusCode": 400, "error": "Missing required parameter: ingest_date"}

    s3_client = _get_s3_client()

    result = generate_report(
        s3_client=s3_client,
        bucket=bucket,
        ingest_date=ingest_date,
        execution_context=execution_context,
    )

    return {
        "statusCode": 200,
        **result,
    }
