"""Lambda handler to load processed KR payloads into DynamoDB."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
import json

from kr_details_pipeline import load


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    import boto3

    bucket = str(event["bucket"])
    table_name = str(event.get("table_name") or os.getenv("DYNAMODB_TABLE") or "TourKoreaDomainData")
    processed_prefix = str(event.get("processed_prefix", "processed/KR"))
    ingest_date = str(event.get("ingest_date") or datetime.utcnow().strftime("%Y%m%d"))
    debug_failures = bool(os.getenv("DEBUG_LOAD_FAILURES") == "1")

    status = "ok"
    passed = 0
    failed = 0

    s3 = boto3.client("s3")
    ddb = boto3.client("dynamodb")

    # Accept optional `prefix` param; fall back to default passed/ path
    prefix = event.get("prefix") or f"{processed_prefix.rstrip('/')}/details/{ingest_date}/passed/"
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = str(item.get("Key", ""))
            if not key.endswith(".json"):
                continue
            try:
                body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
                payload = json.loads(body)
                if debug_failures:
                    result = _load_with_debug(payload, ddb, table_name, max_debug_records=20)
                else:
                    result = load.load_processed_payload(payload, table_name, ddb)
                passed += result.passed
                failed += result.failed
                if result.failed > 0:
                    status = "partial"
            except Exception as exc:  # noqa: BLE001
                failed += 1
                status = "partial"
                print(f"[ERROR] failed to load {key}: {exc}")

    return {
        "statusCode": 200 if status == "ok" else 207,
        "counts": {
            "passed": passed,
            "failed": failed,
            "status": status,
        },
        "ingest_date": ingest_date,
        "loaded_prefix": prefix,
    }


def _load_with_debug(payload: dict[str, Any], client: Any, table_name: str, max_debug_records: int = 20) -> load.LoadResult:
    city_record = payload.get("city_record")
    records = payload.get("records") if isinstance(payload.get("records"), list) else []

    passed = 0
    failed = 0
    debug_printed = 0

    if not isinstance(city_record, dict):
        raise ValueError("processed city payload must include city_record")

    city_pk = f"CITY#{city_record.get('city_name_en')}"
    for item in records:
        try:
            normalized = load._normalize_item(item, city_pk=city_pk)
            load._write_item(client, table_name, normalized)
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            if debug_printed < max_debug_records:
                print(f"[ERROR] failed record city={city_record.get('city_name_en')} content_id={item.get('content_id')}: {exc}")
                debug_printed += 1

    return load.LoadResult(passed, failed)
