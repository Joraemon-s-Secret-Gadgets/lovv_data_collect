#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "boto3>=1.34,<2",
# ]
# ///
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError, ProfileNotFound
from botocore.config import Config


DEFAULT_BUCKET = "lovv-data-pipeline-dev-925273580929"
DEFAULT_FUNCTION_NAME = "kr-pipeline-transform"
DEFAULT_INGEST_DATE = "20260629"
DEFAULT_MANIFEST = Path("data/KR/ingest/20260629_resolved_details/raw_manifest.json")
DEFAULT_OUTPUT = Path(".cache/kr_preprocess_20260629_lambda_results.json")
DEFAULT_PROCESSED_PREFIX = "processed/KR/details"
DEFAULT_PROFILE = "skn26_final"
DEFAULT_REGION = "us-east-1"
DEFAULT_TABLE_NAME = "TourKoreaDomainDataV2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Invoke the KR preprocessing Lambda for every raw manifest key."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--function-name", default=DEFAULT_FUNCTION_NAME)
    parser.add_argument("--table-name", default=DEFAULT_TABLE_NAME)
    parser.add_argument("--processed-prefix", default=DEFAULT_PROCESSED_PREFIX)
    parser.add_argument("--ingest-date", default=DEFAULT_INGEST_DATE)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--read-timeout", type=int, default=900)
    parser.add_argument(
        "--write-summary",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write aggregate quality summary to S3.",
    )
    return parser.parse_args()


def make_session(profile: str | None, region: str) -> boto3.Session:
    if not profile:
        return boto3.Session(region_name=region)
    try:
        return boto3.Session(profile_name=profile, region_name=region)
    except ProfileNotFound:
        print(f"Profile {profile!r} was not found; using default AWS credentials.")
        return boto3.Session(region_name=region)


def load_manifest(path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{path} does not contain a records list.")
    missing = [record for record in records if not record.get("s3_key")]
    if missing:
        raise ValueError(f"{path} contains {len(missing)} record(s) without s3_key.")
    return records


def invoke_one(
    lambda_client: Any,
    *,
    function_name: str,
    bucket: str,
    raw_key: str,
    table_name: str,
    processed_prefix: str,
) -> dict[str, Any]:
    event = {
        "bucket": bucket,
        "raw_key": raw_key,
        "table_name": table_name,
        "processed_prefix": processed_prefix,
        "enrich_wikipedia": True,
        "process_images": True,
    }
    started_at = datetime.now(UTC)
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(event, ensure_ascii=False).encode("utf-8"),
    )
    raw_payload = response["Payload"].read().decode("utf-8")
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        payload = {"raw_payload": raw_payload}
    completed_at = datetime.now(UTC)
    status_code = payload.get("statusCode")
    function_error = response.get("FunctionError")
    ok = response.get("StatusCode") == 200 and status_code == 200 and not function_error
    return {
        "raw_key": raw_key,
        "ok": ok,
        "lambda_status_code": response.get("StatusCode"),
        "handler_status_code": status_code,
        "function_error": function_error,
        "duration_seconds": (completed_at - started_at).total_seconds(),
        "summary": payload.get("summary"),
        "payload": payload if not ok else None,
    }


def count_json_objects(s3_client: Any, *, bucket: str, prefix: str) -> int:
    paginator = s3_client.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith(".json") and not key.endswith("/summary.json"):
                count += 1
    return count


def build_aggregate(
    *,
    args: argparse.Namespace,
    manifest_records: list[dict[str, Any]],
    results: list[dict[str, Any]],
    s3_counts: dict[str, int],
) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    city_ids: defaultdict[str, list[str]] = defaultdict(list)
    failed_results = []

    for result in results:
        summary = result.get("summary")
        if result["ok"] and isinstance(summary, dict):
            for key in (
                "city_metadata",
                "visitor_statistics",
                "attractions",
                "festivals",
                "load_items",
                "passed_items",
                "review_items",
                "failed_items",
            ):
                totals[key] += int(summary.get(key) or 0)
            images = summary.get("images") if isinstance(summary.get("images"), dict) else {}
            for key in ("images_downloaded", "images_failed", "no_source_image", "review_count"):
                totals[f"image_{key}"] += int(images.get(key) or 0)
            wiki = summary.get("wiki") if isinstance(summary.get("wiki"), dict) else {}
            if wiki.get("status"):
                totals[f"wiki_{wiki['status']}"] += 1
            city_id = summary.get("city_id")
            if city_id:
                city_ids[str(city_id)].append(result["raw_key"])
        else:
            failed_results.append(result)

    duplicate_city_ids = {
        city_id: raw_keys for city_id, raw_keys in city_ids.items() if len(raw_keys) > 1
    }
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "function_name": args.function_name,
        "bucket": args.bucket,
        "manifest": str(args.manifest),
        "manifest_record_count": len(manifest_records),
        "invoked": len(results),
        "succeeded": len(results) - len(failed_results),
        "failed_invocations": len(failed_results),
        "table_name": args.table_name,
        "processed_prefix": args.processed_prefix,
        "ingest_date": args.ingest_date,
        "totals": dict(totals),
        "s3_counts": s3_counts,
        "duplicate_city_ids": duplicate_city_ids,
        "failed_raw_keys": [result["raw_key"] for result in failed_results],
    }


def put_summary(s3_client: Any, *, bucket: str, key: str, summary: dict[str, Any]) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = load_manifest(args.manifest)
    session = make_session(args.profile, args.region)
    lambda_client = session.client(
        "lambda",
        config=Config(
            connect_timeout=30,
            read_timeout=args.read_timeout,
            retries={"max_attempts": 2},
        ),
    )
    s3_client = session.client("s3")

    print(f"Invoking {args.function_name} for {len(records)} raw objects.")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(
                invoke_one,
                lambda_client,
                function_name=args.function_name,
                bucket=args.bucket,
                raw_key=record["s3_key"],
                table_name=args.table_name,
                processed_prefix=args.processed_prefix,
            )
            for record in records
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                result = future.result()
            except ClientError as error:
                result = {
                    "raw_key": "<unknown>",
                    "ok": False,
                    "error": str(error),
                    "summary": None,
                }
            results.append(result)
            if index == 1 or index % 20 == 0 or index == len(records):
                ok_count = sum(1 for item in results if item["ok"])
                print(f"Progress: {index}/{len(records)} complete, ok={ok_count}")

    results.sort(key=lambda item: item["raw_key"])
    base_prefix = f"{args.processed_prefix.rstrip('/')}/{args.ingest_date}"
    s3_counts = {
        name: count_json_objects(s3_client, bucket=args.bucket, prefix=f"{base_prefix}/{name}/")
        for name in ("passed", "review", "failed", "quality")
    }
    aggregate = build_aggregate(
        args=args,
        manifest_records=records,
        results=results,
        s3_counts=s3_counts,
    )
    if args.write_summary:
        summary_key = f"{base_prefix}/quality/summary.json"
        put_summary(s3_client, bucket=args.bucket, key=summary_key, summary=aggregate)
        aggregate["summary_s3_key"] = summary_key

    report = {"aggregate": aggregate, "results": results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    return 0 if aggregate["failed_invocations"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
