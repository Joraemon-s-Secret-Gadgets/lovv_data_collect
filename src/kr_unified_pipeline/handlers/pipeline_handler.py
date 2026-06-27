"""Lambda handler for unified preprocessing pipeline E2E operations.

Supports commands:
  - "load": Read processed data from S3 and load into DynamoDB
  - "vector-build": Rebuild vector index from DynamoDB
  - "e2e": Full sequence (load → vector-build)

Requirements: 13.2, 13.3, 13.4, 13.5, 13.7, 13.8, 13.9
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_SUPPORTED_COMMANDS = {"load", "vector-build", "e2e", "preprocess"}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    """Unified pipeline Lambda handler.

    Orchestrates S3 read → DynamoDB load → Vector rebuild based on the
    command specified in the event.

    Args:
        event: Lambda event with keys:
            - command: "load" | "vector-build" | "e2e"
            - bucket: S3 pipeline bucket (optional, overrides env)
            - ingest_date: target ingest date partition (optional)
            - table_name: DynamoDB table name (optional, overrides env)
            - province_id: scope to single province (optional)
            - rebuild_mode: "full" or "incremental" (default "full")
            - vector_bucket: S3 Vectors bucket (optional, overrides env)
            - index_name: vector index name (optional, overrides env)
        context: Lambda context (unused).

    Returns:
        Dict with statusCode (200 or 207) and summary metrics.
    """
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
    vector_bucket = str(
        event.get("vector_bucket")
        or os.environ.get("VECTOR_BUCKET")
        or "lovv-vector-dev"
    )
    index_name = str(
        event.get("index_name")
        or os.environ.get("VECTOR_INDEX")
        or "kr-tour-domain-v1"
    )
    ingest_date = str(event.get("ingest_date") or "")
    province_id = event.get("province_id") or None
    rebuild_mode = str(event.get("rebuild_mode") or "full")

    logger.info(
        "Pipeline handler invoked: command=%s, table=%s, bucket=%s, "
        "vector_bucket=%s, index=%s, ingest_date=%s, province_id=%s, rebuild_mode=%s",
        command, table_name, bucket, vector_bucket, index_name,
        ingest_date, province_id, rebuild_mode,
    )

    # Initialize result tracking
    summary: dict[str, Any] = {
        "command": command,
        "table_name": table_name,
        "bucket": bucket,
        "vector_bucket": vector_bucket,
        "index_name": index_name,
        "ingest_date": ingest_date,
        "province_id": province_id,
        "rebuild_mode": rebuild_mode,
    }

    load_result: dict[str, Any] | None = None
    vector_result: dict[str, Any] | None = None
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

    if command in ("load", "e2e"):
        load_result, load_errors = _execute_load_phase(
            boto3_module=boto3,
            bucket=bucket,
            ingest_date=ingest_date,
            table_name=table_name,
            province_id=province_id,
        )
        errors.extend(load_errors)

        if load_result is None:
            # Non-recoverable error in load phase; skip vector-build
            # Requirement 13.8: preserve completed phase results, skip subsequent
            status_code = 207
            logger.error(
                "Load phase failed with non-recoverable error. "
                "Skipping vector-build phase."
            )
        elif load_result.get("load_failed", 0) > 0:
            status_code = 207

    if command in ("vector-build", "e2e"):
        # Skip vector-build if load phase failed (e2e mode only)
        if command == "e2e" and load_result is None:
            errors.append("Vector-build phase skipped due to load phase failure.")
            logger.warning("Vector-build phase skipped due to load phase failure.")
        else:
            vector_result, vector_errors = _execute_vector_build_phase(
                boto3_module=boto3,
                table_name=table_name,
                vector_bucket=vector_bucket,
                index_name=index_name,
                rebuild_mode=rebuild_mode,
            )
            errors.extend(vector_errors)

            if vector_result is None:
                status_code = 207
            elif vector_result.get("items_skipped", 0) > 0:
                status_code = 207

    # Build combined summary report (Requirement 13.9)
    elapsed = round(time.time() - start_time, 2)
    summary["execution_time_seconds"] = elapsed
    summary["load"] = load_result
    summary["vector"] = vector_result
    summary["errors"] = errors

    # Compute aggregate counts for the summary
    summary["s3_files_read"] = (
        load_result.get("s3_files_read", 0) if load_result else 0
    )
    summary["records_loaded"] = (
        load_result.get("loaded", 0) if load_result else 0
    )
    summary["vectors_upserted"] = (
        vector_result.get("items_upserted", 0) if vector_result else 0
    )

    logger.info(
        "Pipeline handler completed: command=%s, status=%d, elapsed=%.2fs, "
        "s3_files=%d, loaded=%d, vectors=%d, errors=%d",
        command, status_code, elapsed,
        summary["s3_files_read"], summary["records_loaded"],
        summary["vectors_upserted"], len(errors),
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


def _execute_vector_build_phase(
    *,
    boto3_module: Any,
    table_name: str,
    vector_bucket: str,
    index_name: str,
    rebuild_mode: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Execute the vector index rebuild phase.

    Uses kr_vector_index modules (export, chunks, embed, upsert) to rebuild
    the vector index from DynamoDB data.

    Returns:
        Tuple of (result dict or None on failure, list of error messages).
    """
    from kr_vector_index.chunks import build_chunks
    from kr_vector_index.embed import embed_chunks
    from kr_vector_index.export import export_items
    from kr_vector_index.upsert import build_vector_records, put_vectors_sdk

    errors: list[str] = []

    try:
        ddb_client = boto3_module.client("dynamodb")
        bedrock_client = boto3_module.client("bedrock-runtime")
        s3vectors_client = boto3_module.client("s3vectors")

        # Export items from DynamoDB using EntityTypeDomainIndex GSI
        # (Requirement 12.7: use descriptive GSI name for new table)
        items = export_items(
            ddb_client,
            table_name=table_name,
            index_name="EntityTypeDomainIndex",
        )

        logger.info(
            "Vector export complete: %d items from table=%s",
            len(items), table_name,
        )

        if not items:
            result = {
                "items_exported": 0,
                "chunks_created": 0,
                "items_upserted": 0,
                "items_skipped": 0,
                "rebuild_mode": rebuild_mode,
            }
            return result, errors

        # Build chunks from exported items
        chunks = build_chunks(items)

        # Embed chunks using Titan Embed v2
        embeddings = embed_chunks(bedrock_client, chunks)

        # Build vector records and upsert to S3 Vectors
        records = build_vector_records(chunks, embeddings)
        upserted = put_vectors_sdk(
            s3vectors_client,
            records,
            vector_bucket=vector_bucket,
            index_name=index_name,
        )

        items_skipped = len(chunks) - upserted

        result = {
            "items_exported": len(items),
            "chunks_created": len(chunks),
            "items_upserted": upserted,
            "items_skipped": items_skipped,
            "rebuild_mode": rebuild_mode,
        }

        logger.info(
            "Vector build complete: exported=%d, chunks=%d, upserted=%d, skipped=%d",
            len(items), len(chunks), upserted, items_skipped,
        )
        return result, errors

    except Exception as exc:  # noqa: BLE001
        msg = f"Vector build non-recoverable error: {type(exc).__name__}: {exc}"
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
