"""Lambda handler to preprocess one KR raw JSON object into processed S3 outputs."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from kr_details_pipeline import transform
from kr_details_pipeline.domain_preprocess import preprocess_city_payload

_WIKI_COPY_FIELDS = (
    "source_name",
    "source_url",
    "collected_at",
    "field_status",
    "data_confidence",
    "verified_at",
    "verified_source_url",
    "verification_note",
    "prefecture_id",
    "location",
    "latitude",
    "longitude",
    "description",
    "geography_description",
    "climate_table",
    "site_urls",
)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    import boto3

    bucket, raw_key = _extract_s3_target(event)
    table_name = str(event.get("table_name") or os.getenv("DYNAMODB_TABLE") or "TourKoreaDomainData")
    processed_prefix = str(event.get("processed_prefix") or os.getenv("PROCESSED_PREFIX") or "processed/KR/details")
    write_processed = bool(event.get("write_processed", True))

    s3 = boto3.client("s3")

    raw_body = s3.get_object(Bucket=bucket, Key=raw_key)["Body"].read().decode("utf-8")
    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from s3://{bucket}/{raw_key}")

    result = preprocess_city_payload(payload, source_key=raw_key, table_name=table_name)
    wiki_summary = _apply_wikipedia_enrichment(
        s3=s3,
        bucket=bucket,
        raw_key=raw_key,
        event=event,
        result=result,
    )
    passed_records = _passed_records(result)
    passed_records, image_summary = _rewrite_image_urls(
        event=event,
        s3=s3,
        passed_records=passed_records,
        city_name_en=str(result.get("city_record", {}).get("city_name_en") or ""),
    )
    review_records = list(result["review"])
    failed_records = list(result["failed"])

    summary = {
        **result["summary"],
        "status": "ok" if not failed_records else "partial",
        "bucket": bucket,
        "raw_key": raw_key,
        "processed_prefix": processed_prefix,
        "passed_items": len(passed_records),
        "review_items": len(review_records),
        "failed_items": len(failed_records),
        "wiki": wiki_summary,
        "images": image_summary,
        "executed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if write_processed:
        _write_processed_outputs(
            s3=s3,
            bucket=bucket,
            processed_prefix=processed_prefix,
            raw_key=raw_key,
            summary=summary,
            passed_records=passed_records,
            review_records=review_records,
            failed_records=failed_records,
        )

    return {
        "statusCode": 200,
        "summary": summary,
    }


def _extract_s3_target(event: dict[str, Any]) -> tuple[str, str]:
    records = event.get("Records")
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, dict) and isinstance(first.get("s3"), dict):
            bucket = first["s3"]["bucket"]["name"]
            key = first["s3"]["object"]["key"]
            return str(bucket), str(key)

    bucket = event.get("bucket")
    raw_key = event.get("raw_key")
    if not bucket or not raw_key:
        raise ValueError("event must include bucket/raw_key or S3 Records.")
    return str(bucket), str(raw_key)


def _passed_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in result["load_items"]:
        if item.get("quality_status") != "passed":
            continue
        record = dict(item)
        record.pop("table", None)
        records.append(record)
    return records


def _apply_wikipedia_enrichment(
    *,
    s3: Any,
    bucket: str,
    raw_key: str,
    event: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    if not _bool_event_value(event.get("enrich_wikipedia", True)):
        _update_city_metadata(result, {"wiki_status": "disabled"})
        return {"status": "disabled"}

    wiki_key = str(event.get("wikipedia_key") or _default_wikipedia_key(raw_key))
    try:
        body = s3.get_object(Bucket=bucket, Key=wiki_key)["Body"].read().decode("utf-8")
        wiki_payload = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        _update_city_metadata(result, {"wiki_status": "missing", "wiki_source_key": wiki_key})
        return {"status": "missing", "source_key": wiki_key, "error": str(exc)}

    city_item = _first_city_metadata(result)
    wiki_record = _match_wikipedia_record(_wiki_records(wiki_payload), city_item)
    if wiki_record is None:
        _update_city_metadata(result, {"wiki_status": "missing", "wiki_source_key": wiki_key})
        return {"status": "missing", "source_key": wiki_key}

    enrichment = _wikipedia_enrichment(wiki_record, wiki_key)
    _update_city_metadata(result, enrichment)
    return {
        "status": "matched",
        "source_key": wiki_key,
        "city_name_en": str(wiki_record.get("city_name_en") or ""),
    }


def _rewrite_image_urls(
    *,
    event: dict[str, Any],
    s3: Any,
    passed_records: list[dict[str, Any]],
    city_name_en: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not _bool_event_value(event.get("process_images", True)):
        return passed_records, {"status": "disabled", "total_records": len(passed_records)}

    image_bucket = str(event.get("image_bucket") or os.getenv("IMAGE_BUCKET") or "")
    if not image_bucket:
        return passed_records, {"status": "skipped_no_image_bucket", "total_records": len(passed_records)}

    from kr_image_processor.processor import rewrite_image_urls_to_s3

    image_result = rewrite_image_urls_to_s3(
        records=passed_records,
        image_s3_client=s3,
        image_bucket=image_bucket,
        city_name_en=city_name_en,
    )
    rewritten = image_result.pop("records")
    image_result["status"] = "processed"
    return rewritten, image_result


def _default_wikipedia_key(raw_key: str) -> str:
    ingest_date = raw_key.split("/")[-2] if "/" in raw_key else "unknown"
    return f"raw/KR/wikipedia/{ingest_date}/cities.json"


def _first_city_metadata(result: dict[str, Any]) -> dict[str, Any]:
    city_items = result.get("city_metadata")
    if isinstance(city_items, list):
        for item in city_items:
            if isinstance(item, dict):
                return item
    return {}


def _wiki_records(wiki_payload: Any) -> list[dict[str, Any]]:
    if isinstance(wiki_payload, list):
        return [row for row in wiki_payload if isinstance(row, dict)]
    if isinstance(wiki_payload, dict):
        for key in ("cities", "records", "items"):
            rows = wiki_payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _match_wikipedia_record(wiki_records: list[dict[str, Any]], city_item: dict[str, Any]) -> dict[str, Any] | None:
    city_en = _match_key(city_item.get("city_name_en"))
    for row in wiki_records:
        if _match_key(row.get("city_name_en")) == city_en:
            return row

    province = str(city_item.get("province") or "").strip()
    city_ko = str(city_item.get("city_name_ko") or "").strip()
    if not province or not city_ko:
        return None
    for row in wiki_records:
        if str(row.get("province") or "").strip() == province and str(row.get("city_name_ko") or "").strip() == city_ko:
            return row
    return None


def _wikipedia_enrichment(wiki_record: dict[str, Any], wiki_key: str) -> dict[str, Any]:
    enrichment: dict[str, Any] = {
        "wiki_status": "matched",
        "wiki_source_key": wiki_key,
    }
    if wiki_record.get("city_id") not in (None, ""):
        enrichment["wiki_city_id"] = wiki_record["city_id"]
    for field in _WIKI_COPY_FIELDS:
        value = wiki_record.get(field)
        if value not in (None, "", [], {}):
            enrichment[field] = value
    return enrichment


def _update_city_metadata(result: dict[str, Any], fields: dict[str, Any]) -> None:
    for collection_name in ("city_metadata", "load_items"):
        rows = result.get(collection_name)
        if not isinstance(rows, list):
            continue
        for item in rows:
            if isinstance(item, dict) and item.get("entity_type") == "city_metadata":
                item.update(fields)


def _match_key(value: Any) -> str:
    return str(value or "").strip().replace("_", "-").upper()


def _bool_event_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _write_processed_outputs(
    *,
    s3: Any,
    bucket: str,
    processed_prefix: str,
    raw_key: str,
    summary: dict[str, Any],
    passed_records: list[dict[str, Any]],
    review_records: list[dict[str, Any]],
    failed_records: list[dict[str, Any]],
) -> None:
    ingest_date = raw_key.split("/")[-2] if "/" in raw_key else "unknown"
    city_file = raw_key.split("/")[-1]
    city_name = city_file.rsplit(".", 1)[0]
    base_prefix = f"{processed_prefix.rstrip('/')}/{ingest_date}"
    outputs = {
        "passed": {"summary": summary, "records": passed_records},
        "review": {"summary": summary, "records": review_records},
        "failed": {"summary": summary, "records": failed_records},
        "quality": {"summary": summary},
    }
    for stage, body in outputs.items():
        key = f"{base_prefix}/{stage}/{city_name}.json"
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=transform.as_json(body),
            ContentType="application/json",
            Metadata={
                "pipeline_stage": "kr-domain-preprocess",
                "source_key": raw_key,
                "city_name_en": city_name,
            },
        )
