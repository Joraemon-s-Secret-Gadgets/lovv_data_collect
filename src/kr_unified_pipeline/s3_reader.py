"""
S3 processed data reader for the unified pipeline.

Reads pre-processed JSON files from the S3 pipeline bucket at
`processed/KR/details/{ingest_date}/passed/` and returns parsed
domain items ready for DynamoDB loading.

Requirements: 13.1, 13.3, 13.6, 14.3
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# S3 prefix template for processed KR detail files
_PREFIX_TEMPLATE = "processed/KR/details/{ingest_date}/passed/"
_DATE_PREFIX = "processed/KR/details/"


class S3ClientProtocol(Protocol):
    """Minimal S3 client interface required by the reader."""

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...


class S3ProcessedReader:
    """Reads pre-processed JSON domain items from S3 pipeline bucket.

    Lists and reads JSON files from `processed/KR/details/{ingest_date}/passed/`
    prefix. Supports province filtering for local-test mode.

    Args:
        s3_client: A boto3 S3 client (injected dependency).
        bucket: S3 bucket name containing processed data.
        ingest_date: Target ingest date partition (e.g. "20250101").
            If empty/None, the latest available date is auto-detected.
    """

    def __init__(
        self,
        s3_client: S3ClientProtocol,
        bucket: str,
        ingest_date: str | None = None,
    ) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._ingest_date = ingest_date or ""

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def ingest_date(self) -> str:
        return self._ingest_date

    def read_items(self, province_id: str | None = None) -> list[dict[str, Any]]:
        """Read all processed domain items from S3.

        Lists JSON files under the processed prefix, reads and parses each,
        and returns domain items as dicts ready for DynamoDB loading.

        Args:
            province_id: Optional province key to filter items by.
                When provided, only items whose `province_key` matches
                this value are returned (used in local-test mode).

        Returns:
            List of parsed domain item dicts.
        """
        ingest_date = self._resolve_ingest_date()
        if not ingest_date:
            logger.warning("No ingest date available and no dates found in bucket.")
            return []

        self._ingest_date = ingest_date
        prefix = _PREFIX_TEMPLATE.format(ingest_date=ingest_date)
        keys = self._list_json_keys(prefix)

        if not keys:
            logger.info("No JSON files found under prefix: %s", prefix)
            return []

        logger.info(
            "Found %d JSON file(s) under %s in bucket %s",
            len(keys),
            prefix,
            self._bucket,
        )

        items: list[dict[str, Any]] = []
        for key in keys:
            parsed = self._read_and_parse(key)
            items.extend(parsed)

        if province_id:
            items = [
                item for item in items
                if item.get("province_key") == province_id
            ]
            logger.info(
                "Province filter '%s' applied: %d item(s) retained.",
                province_id,
                len(items),
            )

        logger.info("Total items read from S3: %d", len(items))
        return items

    def _resolve_ingest_date(self) -> str:
        """Resolve the ingest date, auto-detecting the latest if not provided."""
        if self._ingest_date:
            return self._ingest_date
        return self._detect_latest_date()

    def _detect_latest_date(self) -> str:
        """List available ingest dates and return the latest one.

        Looks for common prefixes under `processed/KR/details/` to find
        available date partitions.

        Returns:
            The latest date string (e.g. "20250115") or empty string if none found.
        """
        paginator_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Prefix": _DATE_PREFIX,
            "Delimiter": "/",
        }

        dates: list[str] = []
        while True:
            response = self._s3.list_objects_v2(**paginator_kwargs)
            common_prefixes = response.get("CommonPrefixes", [])
            for cp in common_prefixes:
                prefix_str = cp.get("Prefix", "")
                # Extract date from "processed/KR/details/20250115/"
                parts = prefix_str.rstrip("/").split("/")
                if len(parts) >= 4:
                    date_part = parts[3]
                    if date_part.isdigit() and len(date_part) == 8:
                        dates.append(date_part)

            if response.get("IsTruncated"):
                paginator_kwargs["ContinuationToken"] = response["NextContinuationToken"]
            else:
                break

        if not dates:
            logger.warning("No ingest date partitions found under %s", _DATE_PREFIX)
            return ""

        latest = sorted(dates)[-1]
        logger.info("Auto-detected latest ingest date: %s", latest)
        return latest

    def _list_json_keys(self, prefix: str) -> list[str]:
        """List all .json object keys under the given S3 prefix.

        Handles pagination for buckets with many objects.

        Args:
            prefix: S3 key prefix to list under.

        Returns:
            List of S3 object keys ending in .json.
        """
        keys: list[str] = []
        paginator_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Prefix": prefix,
        }

        while True:
            response = self._s3.list_objects_v2(**paginator_kwargs)
            contents = response.get("Contents", [])
            for obj in contents:
                key = obj.get("Key", "")
                if key.endswith(".json"):
                    keys.append(key)

            if response.get("IsTruncated"):
                paginator_kwargs["ContinuationToken"] = response["NextContinuationToken"]
            else:
                break

        return keys

    def _read_and_parse(self, key: str) -> list[dict[str, Any]]:
        """Read a single S3 JSON file and parse its contents.

        Supports both single-object JSON files (returning a one-item list)
        and JSON files containing a list of items at the top level.

        Args:
            key: S3 object key to read.

        Returns:
            List of parsed domain item dicts from the file.
        """
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read()
            data = json.loads(body)
        except Exception as exc:
            logger.error("Failed to read/parse S3 object %s: %s", key, exc)
            return []

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            # Single item file or a wrapper with "records" key
            if "records" in data and isinstance(data["records"], list):
                return [item for item in data["records"] if isinstance(item, dict)]
            return [data]
        else:
            logger.warning("Unexpected JSON structure in %s, skipping.", key)
            return []
