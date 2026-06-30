from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_SUPPORTED_COMMANDS = {"load", "preprocess"}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    import boto3

    start_time = time.time()

    command = str(event.get("command") or "")
    if command not in _SUPPORTED_COMMANDS:
        return {
            "statusCode": 400,
            "error": f"Unsupported command: '{command}'. Must be one of: {sorted(_SUPPORTED_COMMANDS)}",
        }

    # Read configuration from event fields with environment variable fallbacks
    table_name = str(
        event.get("table_name")
        or os.environ.get("DYNAMODB_TABLE")
        or "TourKoreaDomainDataV2"
    )
    bucket = str(
        event.get("bucket")
        or os.environ.get("PIPELINE_BUCKET")
        or ""
    )
    ingest_date = str(event.get("ingest_date") or "")
    province_id = event.get("province_id") or None

    logger.info(
        "Pipeline handler invoked: command=%s, table=%s, bucket=%s, ingest_date=%s, province_id=%s",
        command, table_name, bucket, ingest_date, province_id,
    )

    # Initialize result tracking
    summary: dict[str, Any] = {
        "command": command,
        "table_name": table_name,
        "bucket": bucket,
        "ingest_date": ingest_date,
        "province_id": province_id,
    }

    load_result: dict[str, Any] | None = None
    errors: list[str] = []
    status_code = 200

    # Execute phases based on command
    if command == "preprocess":
        preprocess_result, preprocess_errors = _execute_preprocess_phase(
            event=event,
            province_id=province_id,
        )
        errors.extend(preprocess_errors)
        elapsed = round(time.time() - start_time, 2)
        summary["execution_time_seconds"] = elapsed
        summary["preprocess"] = preprocess_result
        summary["errors"] = errors

        if preprocess_result is None or preprocess_errors:
            status_code = 207

        logger.info(
            "Pipeline handler completed: command=%s, status=%d, elapsed=%.2fs",
            command, status_code, elapsed,
        )
        return {"statusCode": status_code, "summary": summary}

    if command == "load":
        load_result, load_errors = _execute_load_phase(
            boto3_module=boto3,
            bucket=bucket,
            ingest_date=ingest_date,
            table_name=table_name,
            province_id=province_id,
        )
        errors.extend(load_errors)

        if load_result is None:
            status_code = 207
            logger.error("Load phase failed with non-recoverable error.")
        elif load_result.get("load_failed", 0) > 0:
            status_code = 207

    # Build combined summary report (Requirement 13.9)
    elapsed = round(time.time() - start_time, 2)
    summary["execution_time_seconds"] = elapsed
    summary["load"] = load_result
    summary["errors"] = errors

    # Compute aggregate counts for the summary
    summary["s3_files_read"] = (
        load_result.get("s3_files_read", 0) if load_result else 0
    )
    summary["records_loaded"] = (
        load_result.get("loaded", 0) if load_result else 0
    )

    logger.info(
        "Pipeline handler completed: command=%s, status=%d, elapsed=%.2fs, "
        "s3_files=%d, loaded=%d, errors=%d",
        command, status_code, elapsed,
        summary["s3_files_read"], summary["records_loaded"],
        len(errors),
    )

    return {
        "statusCode": status_code,
        "summary": summary,
    }


def _execute_load_phase(
    *,
    boto3_module: Any,
    bucket: str,
    ingest_date: str,
    table_name: str,
    province_id: str | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Execute the S3 read → DynamoDB load phase.

    Uses S3ProcessedReader to read items and kr_details_pipeline.load._write_item
    to write each item to DynamoDB.

    Returns:
        Tuple of (result dict or None on failure, list of error messages).
    """
    from kr_unified_pipeline.s3_reader import S3ProcessedReader
    from kr_details_pipeline.load import _write_item

    errors: list[str] = []

    if not bucket:
        msg = "Load phase requires a bucket name (set PIPELINE_BUCKET env var or pass 'bucket' in event)."
        logger.error(msg)
        errors.append(msg)
        return None, errors

    try:
        s3_client = boto3_module.client("s3")
        ddb_client = boto3_module.client("dynamodb")

        # Read processed items from S3
        reader = S3ProcessedReader(
            s3_client=s3_client,
            bucket=bucket,
            ingest_date=ingest_date or None,
        )
        items = reader.read_items(province_id=province_id)
        ingest_date_used = reader.ingest_date

        logger.info(
            "S3 read complete: %d items from bucket=%s, ingest_date=%s",
            len(items), bucket, ingest_date_used,
        )

        # Load items into DynamoDB
        loaded = 0
        failed = 0
        failures: list[dict[str, str]] = []

        for item in items:
            try:
                ddb_item = dict(item)
                ddb_item.pop("table", None)
                # Add GSI key fields for V2 table if missing
                if "domain_sort_key" not in ddb_item:
                    entity_type = ddb_item.get("entity_type", "")
                    content_id = ddb_item.get("content_id", "")
                    entity_id = ddb_item.get("entity_id", "")
                    ddb_item["city_key"] = ddb_item.get("PK", "") or "UNKNOWN"
                    ddb_item["province_key"] = ddb_item.get("province_key") or ddb_item.get("province", "") or "UNKNOWN"
                    ddb_item["domain_sort_key"] = f"{entity_type}#{content_id}" if content_id else f"{entity_type}#{entity_id}" if entity_id else f"{entity_type}#UNKNOWN"
                    if entity_type == "festival":
                        month = ddb_item.get("month") or (ddb_item.get("eventstartdate") or "")[:2] or "00"
                        ddb_item["gsi_sk"] = f"FESTIVAL#{month}#{content_id}"
                    else:
                        ddb_item["gsi_sk"] = f"{entity_type}#{content_id}" if content_id else f"{entity_type}#{entity_id}" if entity_id else f"{entity_type}#UNKNOWN"
                _write_item(ddb_client, table_name, ddb_item)
                loaded += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                item_id = str(item.get("PK") or item.get("city_id") or "unknown")
                error_msg = f"DynamoDB write failed for {item_id}: {type(exc).__name__}: {exc}"
                failures.append({"item_id": item_id, "error": str(exc)})
                errors.append(error_msg)
                logger.error(error_msg)

        result = {
            "s3_files_read": len(items),
            "ingest_date": ingest_date_used,
            "loaded": loaded,
            "load_failed": failed,
            "failures": failures[:20],  # Cap failure details
        }

        logger.info(
            "Load phase complete: loaded=%d, failed=%d", loaded, failed
        )
        return result, errors

    except Exception as exc:  # noqa: BLE001
        msg = f"Load phase non-recoverable error: {type(exc).__name__}: {exc}"
        logger.error(msg)
        errors.append(msg)
        return None, errors


def _execute_preprocess_phase(
    *,
    event: dict[str, Any],
    province_id: str | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Execute the preprocessing phase via UnifiedPipeline orchestrator.

    Delegates to orchestrator.UnifiedPipeline for preprocessing commands.
    Requirement 1.1, 13.2: handler delegates to orchestrator for preprocess.

    Returns:
        Tuple of (result dict or None on failure, list of error messages).
    """
    from kr_unified_pipeline.models import PipelineConfig
    from kr_unified_pipeline.orchestrator import UnifiedPipeline

    errors: list[str] = []

    try:
        stages = event.get("stages") or []
        config = PipelineConfig(
            output_dir=str(event.get("output_dir", "data/KR/")),
            stages=stages if isinstance(stages, list) else [stages],
            province_id=province_id,
            force_refresh=bool(event.get("force_refresh", False)),
            skip_images=bool(event.get("skip_images", False)),
            force_image_update=bool(event.get("force_image_update", False)),
            verbose=bool(event.get("verbose", False)),
        )

        pipeline = UnifiedPipeline(config=config)
        context = pipeline.run()

        summary = pipeline.get_summary(context)
        errors.extend(context.errors)

        return summary, errors

    except Exception as exc:  # noqa: BLE001
        msg = f"Preprocess phase non-recoverable error: {type(exc).__name__}: {exc}"
        logger.error(msg)
        errors.append(msg)
        return None, errors
