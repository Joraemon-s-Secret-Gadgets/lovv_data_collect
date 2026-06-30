"""Lambda handler for KR S3 Vector index build operations."""

from __future__ import annotations

import json
import os
from typing import Any

from kr_vector_index.aggregate import build_aggregate_response
from kr_vector_index.batch import (
    DEFAULT_BATCH_SIZE,
    build_batch_plan,
    fetch_vectorizable_items_by_pk,
    slice_batch_items,
)
from kr_vector_index.chunks import build_chunks
from kr_vector_index.embed import embed_chunks
from kr_vector_index.export import count_by_entity_type, export_items
from kr_vector_index.manifest import build_manifest
from kr_vector_index.preflight import build_preflight_summary
from kr_vector_index.upsert import build_vector_records, put_vectors_sdk

DEFAULT_TABLE_NAME = "TourKoreaDomainDataV2"
DEFAULT_VECTOR_INDEX_NAME = "kr-tour-domain-v2"
DEFAULT_ENTITY_INDEX_NAME = "EntityTypeDomainIndex"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    command = str(event.get("command") or "export-counts")
    if command not in {"export-counts", "build", "preflight", "plan", "worker", "aggregate"}:
        return {"statusCode": 400, "error": f"unsupported command: {command}"}

    dry_run = bool(event.get("dry_run", False))

    import boto3

    table_name = str(
        event.get("table_name")
        or os.environ.get("DYNAMODB_TABLE")
        or DEFAULT_TABLE_NAME
    )
    vector_bucket = str(
        event.get("vector_bucket")
        or os.environ.get("VECTOR_BUCKET")
        or "lovv-vector-dev"
    )
    index_name = str(
        event.get("index_name")
        or os.environ.get("VECTOR_INDEX")
        or DEFAULT_VECTOR_INDEX_NAME
    )
    entity_index_name = str(
        event.get("entity_index_name")
        or os.environ.get("DYNAMODB_ENTITY_INDEX")
        or DEFAULT_ENTITY_INDEX_NAME
    )
    enrichment_mode = str(event.get("enrichment_mode") or "")
    visitor_statistics_coverage_ok = event.get("visitor_statistics_coverage_ok")
    manifest_bucket = str(
        event.get("manifest_bucket") or os.environ.get("MANIFEST_BUCKET") or ""
    )
    manifest_prefix = str(
        event.get("manifest_prefix")
        or os.environ.get("MANIFEST_PREFIX")
        or "processed/KR/vector/manifests"
    )
    if command == "aggregate":
        return build_aggregate_response(
            event,
            index_name=index_name,
            manifest_bucket=manifest_bucket,
            manifest_prefix=manifest_prefix,
            s3_client_factory=boto3.client,
        )

    city_pk = event.get("city_pk")
    max_items = _positive_int(event.get("max_items"))
    batch_size = _positive_int(event.get("batch_size")) or DEFAULT_BATCH_SIZE
    ddb = boto3.client("dynamodb")

    if command == "preflight":
        summary = build_preflight_summary(
            ddb,
            table_name=table_name,
            entity_index_name=entity_index_name,
        )
        return {
            "statusCode": 200,
            "summary": {
                "command": command,
                "table_name": table_name,
                "entity_index_name": entity_index_name,
                **summary,
            },
        }

    if command == "worker":
        batch = event.get("batch") or event
        batch_id = str(batch.get("batch_id") or "")
        batch_city_pk = str(batch.get("city_pk") or "")
        if not batch_id or not batch_city_pk:
            return {"statusCode": 400, "error": "worker requires batch_id and city_pk"}
        batch_table_name = str(batch.get("table_name") or table_name)
        batch_vector_bucket = str(batch.get("vector_bucket") or vector_bucket)
        batch_index_name = str(batch.get("index_name") or index_name)
        start_offset = int(batch.get("start_offset") or 0)
        batch_max_items = _positive_int(batch.get("max_items")) or batch_size
        city_items = fetch_vectorizable_items_by_pk(
            ddb,
            table_name=batch_table_name,
            city_pk=batch_city_pk,
        )
        items = slice_batch_items(
            city_items,
            start_offset=start_offset,
            max_items=batch_max_items,
        )
        chunks = build_chunks(items)
        vector_success_count = 0
        if not dry_run and chunks:
            bedrock = boto3.client("bedrock-runtime")
            s3vectors = boto3.client("s3vectors")
            embeddings = embed_chunks(bedrock, chunks)
            records = build_vector_records(chunks, embeddings)
            vector_success_count = put_vectors_sdk(
                s3vectors,
                records,
                vector_bucket=batch_vector_bucket,
                index_name=batch_index_name,
            )
        return {
            "statusCode": 200,
            "summary": {
                "command": command,
                "batch_id": batch_id,
                "city_pk": batch_city_pk,
                "start_offset": start_offset,
                "max_items": batch_max_items,
                "table_name": batch_table_name,
                "vector_bucket": batch_vector_bucket,
                "index_name": batch_index_name,
                "item_count": len(items),
                "chunk_count": len(chunks),
                "vector_success_count": vector_success_count,
                "failed_count": 0,
            },
        }

    items = export_items(
        ddb,
        table_name=table_name,
        city_pk=str(city_pk) if city_pk else None,
        index_name=entity_index_name,
    )
    if max_items:
        items = items[:max_items]
    entity_counts = count_by_entity_type(items)

    if command == "plan":
        batches = build_batch_plan(
            items,
            batch_size=batch_size,
            table_name=table_name,
            entity_index_name=entity_index_name,
            vector_bucket=vector_bucket,
            index_name=index_name,
        )
        return {
            "statusCode": 200,
            "summary": {
                "command": command,
                "table_name": table_name,
                "entity_index_name": entity_index_name,
                "vector_bucket": vector_bucket,
                "index_name": index_name,
                "batch_size": batch_size,
                "batch_count": len(batches),
                "item_count": len(items),
                "entity_counts": entity_counts,
                "enrichment_mode": enrichment_mode,
                "visitor_statistics_coverage_ok": visitor_statistics_coverage_ok,
            },
            "batches": batches,
        }

    if command == "export-counts":
        return {
            "statusCode": 200,
            "summary": {
                "command": command,
                "table_name": table_name,
                "entity_index_name": entity_index_name,
                "city_pk": city_pk,
                "entity_counts": entity_counts,
                "item_count": len(items),
            },
        }

    chunks = build_chunks(items)
    vector_success_count = 0
    if not dry_run:
        bedrock = boto3.client("bedrock-runtime")
        s3vectors = boto3.client("s3vectors")
        embeddings = embed_chunks(bedrock, chunks)
        records = build_vector_records(chunks, embeddings)
        vector_success_count = put_vectors_sdk(
            s3vectors,
            records,
            vector_bucket=vector_bucket,
            index_name=index_name,
        )

    manifest = build_manifest(
        index_name=index_name,
        entity_counts=entity_counts,
        chunk_count=len(chunks),
        vector_success_count=vector_success_count,
    )
    manifest_s3_uri = None
    if manifest_bucket:
        manifest_s3_uri = _put_manifest(
            boto3.client("s3"),
            bucket=manifest_bucket,
            prefix=manifest_prefix,
            manifest=manifest,
        )

    return {
        "statusCode": 200,
        "summary": {
            "command": command,
            "dry_run": dry_run,
            "table_name": table_name,
            "entity_index_name": entity_index_name,
            "vector_bucket": vector_bucket,
            "index_name": index_name,
            "city_pk": city_pk,
            "max_items": max_items,
            "entity_counts": entity_counts,
            "item_count": len(items),
            "chunk_count": len(chunks),
            "vector_success_count": vector_success_count,
            "manifest_s3_uri": manifest_s3_uri,
        },
        "manifest": manifest,
    }


def _positive_int(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError("max_items must be >= 1")
    return parsed


def _put_manifest(
    client: Any, *, bucket: str, prefix: str, manifest: dict[str, Any]
) -> str:
    key = f"{prefix.strip('/')}/latest.json"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )
    return f"s3://{bucket}/{key}"
