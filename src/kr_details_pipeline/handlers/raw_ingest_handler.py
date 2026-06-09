"""Lambda-compatible handler for KR details S3 Raw ingest."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from kr_details_pipeline.raw_ingest import RawIngestConfig, ingest_raw_details


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import boto3

    bucket = str(event["bucket"])
    input_dir = Path(str(event.get("input_dir", "data/KR/details")))
    output_dir = Path(str(event.get("output_dir", "data/KR/ingest")))
    ingest_date = str(event.get("ingest_date") or datetime.now().strftime("%Y%m%d"))
    overwrite = bool(event.get("overwrite", False))

    results = ingest_raw_details(
        RawIngestConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            bucket=bucket,
            ingest_date=ingest_date,
            overwrite=overwrite,
        ),
        boto3.client("s3"),
    )
    counts = {
        "uploaded": sum(1 for result in results if result.status == "uploaded"),
        "skipped": sum(1 for result in results if result.status == "skipped"),
        "failed": sum(1 for result in results if result.status == "failed"),
    }
    return {
        "statusCode": 200 if counts["failed"] == 0 else 207,
        "counts": counts,
    }
