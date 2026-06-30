"""City-level image processing for the KR data pipeline.

Downloads images from external URLs, uploads them to the pipeline Image_Bucket,
and replaces record image_url fields with the S3 URL. Records with missing or
failed images are marked for review.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from kr_image_uploader.download import fetch_bytes
from kr_image_uploader.romanize import romanize
from kr_image_uploader.s3_keys import build_image_key

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 1  # seconds
_IMAGE_ENTITY_TYPES = {"attraction", "festival"}


def _is_empty_url(url: Any) -> bool:
    """Return True if url is None, empty, or whitespace-only."""
    if url is None:
        return True
    if not isinstance(url, str):
        return True
    return url.strip() == ""


def _download_with_retry(url: str, retries: int = _MAX_RETRIES) -> bytes:
    """Download image bytes with exponential backoff retry.

    Raises the last exception if all retries are exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_bytes(url, timeout=30)
        except (HTTPError, URLError, OSError) as exc:
            last_error = exc
            if attempt < retries - 1:
                sleep_time = _BACKOFF_BASE * (2 ** attempt)  # 1s, 2s, 4s
                time.sleep(sleep_time)
    raise last_error  # type: ignore[misc]


def _build_filename(record: dict[str, Any], used_names: set[str]) -> str:
    """Build a romanized filename base from the record title.

    Falls back to content_id if title cannot be romanized. Disambiguates
    duplicates by appending the content_id.
    """
    title = str(record.get("title", "") or "")
    content_id = str(record.get("content_id", "") or record.get("contentid", "") or "")
    base = romanize(title) or content_id or "item"
    if base in used_names:
        base = f"{base}_{content_id}"
    used_names.add(base)
    return base


def _get_extension_from_url(url: str) -> str:
    """Extract the file extension from a URL, defaulting to 'jpg'."""
    # Strip query params
    path = url.split("?")[0].split("#")[0]
    if "." in path:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp"):
            return ext
    return "jpg"


def rewrite_image_urls_to_s3(
    *,
    records: list[dict[str, Any]],
    image_s3_client: Any,
    image_bucket: str,
    city_name_en: str,
) -> dict[str, Any]:
    images_downloaded = 0
    images_failed = 0
    no_source_image = 0
    review_entries: list[dict[str, Any]] = []
    used_names: set[str] = set()
    output_records: list[dict[str, Any]] = []

    for source_record in records:
        record = dict(source_record)
        if str(record.get("entity_type") or "") not in _IMAGE_ENTITY_TYPES:
            output_records.append(record)
            continue

        image_url = record.get("image_url")
        if _is_empty_url(image_url):
            image_url = record.get("firstimage")

        if _is_empty_url(image_url):
            no_source_image += 1
            record["image_url"] = ""
            record["source_image_url"] = ""
            record["image_status"] = "needs_review"
            record["image_review_reason"] = "no_source_image"
            review_entries.append(
                _image_review_entry(
                    record=record,
                    city_name_en=city_name_en,
                    original_image_url="",
                    failure_reason="no_source_image",
                    error_message="",
                )
            )
            output_records.append(record)
            continue

        original_image_url = str(image_url)
        if not _is_supported_image_url(original_image_url):
            images_failed += 1
            record["image_url"] = ""
            record["source_image_url"] = original_image_url
            record["image_status"] = "needs_review"
            record["image_review_reason"] = "unsupported_url_scheme"
            record["image_error_message"] = "Only http and https image URLs are supported."
            review_entries.append(
                _image_review_entry(
                    record=record,
                    city_name_en=city_name_en,
                    original_image_url=original_image_url,
                    failure_reason="unsupported_url_scheme",
                    error_message=record["image_error_message"],
                )
            )
            output_records.append(record)
            continue

        filename_base = _build_filename(record, used_names)
        ext = _get_extension_from_url(original_image_url)
        suffix = "1"

        try:
            image_bytes = _download_with_retry(original_image_url)
            s3_key = build_image_key(
                city_name_en=city_name_en,
                file_base=filename_base,
                suffix=suffix,
                ext=ext,
            )
            image_s3_client.put_object(
                Bucket=image_bucket,
                Key=s3_key,
                Body=image_bytes,
                ContentType=f"image/{ext}",
            )
        except Exception as exc:
            images_failed += 1
            record["image_url"] = ""
            record["source_image_url"] = original_image_url
            record["image_status"] = "needs_review"
            record["image_review_reason"] = "download_or_upload_failed"
            record["image_error_message"] = str(exc)
            review_entries.append(
                _image_review_entry(
                    record=record,
                    city_name_en=city_name_en,
                    original_image_url=original_image_url,
                    failure_reason="download_failed",
                    error_message=str(exc),
                )
            )
            output_records.append(record)
            continue

        s3_url = f"https://{image_bucket}.s3.amazonaws.com/{s3_key}"
        record["image_url"] = s3_url
        record["source_image_url"] = original_image_url
        record["image_status"] = "ok"
        record["image_s3_key"] = s3_key
        images_downloaded += 1
        output_records.append(record)

    return {
        "records": output_records,
        "total_records": len(records),
        "images_downloaded": images_downloaded,
        "images_failed": images_failed,
        "no_source_image": no_source_image,
        "review_count": len(review_entries),
        "review_entries": review_entries,
    }


def _image_review_entry(
    *,
    record: dict[str, Any],
    city_name_en: str,
    original_image_url: str,
    failure_reason: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "city_name_en": city_name_en,
        "content_id": str(record.get("content_id") or record.get("contentid") or ""),
        "entity_type": str(record.get("entity_type", "")),
        "original_image_url": original_image_url,
        "failure_reason": failure_reason,
        "error_message": error_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _is_supported_image_url(url: str) -> bool:
    return urlparse(url).scheme.lower() in {"http", "https"}


def process_city(
    s3_client: Any,
    image_s3_client: Any,
    bucket: str,
    image_bucket: str,
    ingest_date: str,
    city_name_en: str,
    source_key: str,
) -> dict[str, Any]:
    """Process all images for a single city.

    Downloads images from external URLs, uploads to Image_Bucket, replaces
    image_url in records with S3 URLs, and writes output to S3.

    Parameters
    ----------
    s3_client : boto3 S3 client
        Client for the pipeline data bucket (read source, write output).
    image_s3_client : boto3 S3 client
        Client for the image bucket (write images). Can be the same as s3_client
        if both buckets are in the same account/region.
    bucket : str
        Pipeline data bucket name.
    image_bucket : str
        Image bucket name (e.g. lovv-pipeline-images-dev-...).
    ingest_date : str
        Ingest date in YYYYMMDD format.
    city_name_en : str
        English city name.
    source_key : str
        S3 key to the city JSON file in the pipeline data bucket.

    Returns
    -------
    dict
        Summary with keys: total_records, images_downloaded, images_failed,
        no_source_image, review_count, review_entries.
    """
    # Read city JSON from S3
    response = s3_client.get_object(Bucket=bucket, Key=source_key)
    body = response["Body"].read()
    city_data = json.loads(body)

    records = city_data.get("records", [])
    # Support raw format: attractions + festivals (no "records" key)
    if not records:
        attractions = city_data.get("attractions", [])
        festivals = city_data.get("festivals", [])
        records = []
        for item in attractions:
            if isinstance(item, dict):
                item.setdefault("entity_type", "attraction")
                records.append(item)
        for item in festivals:
            if isinstance(item, dict):
                item.setdefault("entity_type", "festival")
                records.append(item)

    image_result = rewrite_image_urls_to_s3(
        records=records,
        image_s3_client=image_s3_client,
        image_bucket=image_bucket,
        city_name_en=city_name_en,
    )
    output_records = image_result.pop("records")

    # Write output records to S3
    output_key = f"processed/KR/details/{ingest_date}/images/{city_name_en}.json"
    output_body = json.dumps(output_records, ensure_ascii=False)
    s3_client.put_object(
        Bucket=bucket,
        Key=output_key,
        Body=output_body.encode("utf-8"),
        ContentType="application/json",
    )

    return image_result
