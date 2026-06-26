"""Review manifest aggregation for the KR data pipeline.

Collects review entries from all per-city image processing results and writes
a combined manifest to S3.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def aggregate_review(
    s3_client: Any,
    bucket: str,
    ingest_date: str,
    image_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate review entries from all city results into a single manifest.

    Collects all ``review_entries`` from per-city image processing results,
    writes the combined manifest to S3, and returns a summary.

    Parameters
    ----------
    s3_client : boto3 S3 client
        Client for the pipeline data bucket.
    bucket : str
        Pipeline data bucket name.
    ingest_date : str
        Ingest date in YYYYMMDD format.
    image_results : list[dict]
        Per-city results from the image processing stage. Each dict is expected
        to contain a ``review_entries`` list.

    Returns
    -------
    dict
        Summary with keys: total_review, review_by_reason.
    """
    all_entries: list[dict[str, Any]] = []

    for city_result in image_results:
        entries = city_result.get("review_entries", [])
        all_entries.extend(entries)

    # Count by failure reason
    review_by_reason: dict[str, int] = {}
    for entry in all_entries:
        reason = entry.get("failure_reason", "unknown")
        review_by_reason[reason] = review_by_reason.get(reason, 0) + 1

    # Write combined manifest to S3
    manifest_key = f"processed/KR/review/{ingest_date}/image_review.json"
    manifest_body = json.dumps(all_entries, ensure_ascii=False)

    s3_client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=manifest_body.encode("utf-8"),
        ContentType="application/json",
    )

    total_review = len(all_entries)

    logger.info(
        "Review manifest written: %s (%d entries)",
        manifest_key,
        total_review,
    )

    return {
        "total_review": total_review,
        "review_by_reason": review_by_reason,
    }
