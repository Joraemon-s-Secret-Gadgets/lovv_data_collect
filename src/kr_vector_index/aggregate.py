from __future__ import annotations

import json
from typing import Any

from kr_vector_index.batch import aggregate_batch_results, build_batch_manifest


def build_aggregate_response(
    event: dict[str, Any],
    *,
    index_name: str,
    manifest_bucket: str,
    manifest_prefix: str,
    s3_client_factory: Any,
) -> dict[str, Any]:
    summary = aggregate_batch_results(event.get("batch_results") or [])
    raw_entity_counts = event.get("entity_counts") or {}
    entity_counts = (
        {str(key): int(value) for key, value in raw_entity_counts.items()}
        if isinstance(raw_entity_counts, dict)
        else {}
    )
    manifest = build_batch_manifest(
        index_name=index_name,
        entity_counts=entity_counts,
        aggregate_summary=summary,
    )
    manifest_s3_uri = None
    if manifest_bucket:
        manifest_s3_uri = _put_manifest(
            s3_client_factory("s3"),
            bucket=manifest_bucket,
            prefix=manifest_prefix,
            manifest=manifest,
        )
    summary["manifest_s3_uri"] = manifest_s3_uri
    return {"statusCode": 200, "summary": summary, "manifest": manifest}


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
