"""S3 uploader module for KR Wikipedia crawling results.

Uploads cities.json and prefectures.json to S3 with checksum-based
deduplication. boto3 is lazy-imported only when no S3 client is provided.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

TARGET_FILES = ("cities.json", "prefectures.json")


class S3Client(Protocol):
    """Protocol for S3 client operations used by the uploader."""

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class S3UploadConfig:
    """Configuration for S3 upload."""

    bucket: str
    prefix: str = "raw/KR/wikipedia"
    ingest_date: str = ""  # YYYYMMDD, empty = use current date


@dataclass(frozen=True)
class UploadResult:
    """Result of a single file upload attempt."""

    local_path: str
    s3_key: str
    bucket: str
    status: str  # "uploaded" | "skipped" | "failed"
    error: str | None = None


def _compute_md5(file_path: Path) -> str:
    """Compute MD5 hex digest of a file."""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()


def _resolve_ingest_date(ingest_date: str) -> str:
    """Resolve ingest date: use provided value or current date in YYYYMMDD."""
    if ingest_date:
        # Normalize YYYY-MM-DD to YYYYMMDD
        return ingest_date.replace("-", "")
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _should_skip_upload(
    s3_client: S3Client, bucket: str, key: str, local_md5: str
) -> bool:
    """Check if file already exists in S3 with matching checksum."""
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        existing_md5 = response.get("Metadata", {}).get("content-md5", "")
        if existing_md5 == local_md5:
            return True
    except Exception:
        # Object doesn't exist or access error — proceed with upload
        pass
    return False


def upload_crawl_results(
    output_dir: Path,
    config: S3UploadConfig,
    s3_client: S3Client | None = None,
) -> list[UploadResult]:
    """Upload cities.json and prefectures.json from output_dir to S3.

    S3 key pattern: {prefix}/{ingest_date}/cities.json
                    {prefix}/{ingest_date}/prefectures.json

    If s3_client is None, create one using boto3 (lazy import).
    If ingest_date is empty, use current date in YYYYMMDD format.

    Checksum-based deduplication:
    1. Compute MD5 of local file
    2. HEAD the target S3 key to get existing metadata
    3. If metadata contains matching checksum, skip upload
    4. Otherwise, PUT the file with checksum metadata

    Returns list of UploadResult for each file.
    """
    if s3_client is None:
        import boto3  # lazy import

        s3_client = boto3.client("s3")

    ingest_date = _resolve_ingest_date(config.ingest_date)
    results: list[UploadResult] = []

    for filename in TARGET_FILES:
        file_path = output_dir / filename
        s3_key = f"{config.prefix}/{ingest_date}/{filename}"

        if not file_path.exists():
            results.append(
                UploadResult(
                    local_path=str(file_path),
                    s3_key=s3_key,
                    bucket=config.bucket,
                    status="failed",
                    error=f"File not found: {file_path}",
                )
            )
            continue

        try:
            local_md5 = _compute_md5(file_path)

            # Check for existing object with matching checksum
            if _should_skip_upload(s3_client, config.bucket, s3_key, local_md5):
                logger.info("Skipping %s (checksum match)", s3_key)
                results.append(
                    UploadResult(
                        local_path=str(file_path),
                        s3_key=s3_key,
                        bucket=config.bucket,
                        status="skipped",
                    )
                )
                continue

            # Upload with checksum metadata
            with open(file_path, "rb") as f:
                s3_client.put_object(
                    Bucket=config.bucket,
                    Key=s3_key,
                    Body=f.read(),
                    ContentType="application/json",
                    Metadata={"content-md5": local_md5},
                )

            logger.info("Uploaded %s to s3://%s/%s", file_path, config.bucket, s3_key)
            results.append(
                UploadResult(
                    local_path=str(file_path),
                    s3_key=s3_key,
                    bucket=config.bucket,
                    status="uploaded",
                )
            )

        except Exception as e:
            logger.error("Failed to upload %s: %s", file_path, e)
            results.append(
                UploadResult(
                    local_path=str(file_path),
                    s3_key=s3_key,
                    bucket=config.bucket,
                    status="failed",
                    error=str(e),
                )
            )

    return results
