"""
Unit tests for S3ProcessedReader.

Validates Requirements 13.1, 13.3, 13.6, 14.3.
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from kr_unified_pipeline.s3_reader import S3ProcessedReader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_s3_client(
    list_responses: list[dict[str, Any]] | None = None,
    get_responses: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock S3 client with configurable responses."""
    client = MagicMock()

    if list_responses:
        client.list_objects_v2.side_effect = list_responses
    else:
        client.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}

    if get_responses:
        def _get_object(**kwargs: Any) -> dict[str, Any]:
            key = kwargs["Key"]
            body_data = get_responses.get(key, b"[]")
            body = MagicMock()
            body.read.return_value = (
                body_data if isinstance(body_data, bytes) else json.dumps(body_data).encode()
            )
            return {"Body": body}

        client.get_object.side_effect = _get_object

    return client


# ---------------------------------------------------------------------------
# Tests: Basic functionality
# ---------------------------------------------------------------------------


class TestS3ProcessedReaderInit:
    """Test reader initialization."""

    def test_stores_bucket_and_date(self) -> None:
        client = _make_s3_client()
        reader = S3ProcessedReader(client, bucket="my-bucket", ingest_date="20250115")
        assert reader.bucket == "my-bucket"
        assert reader.ingest_date == "20250115"

    def test_empty_ingest_date_defaults_to_empty_string(self) -> None:
        client = _make_s3_client()
        reader = S3ProcessedReader(client, bucket="my-bucket", ingest_date=None)
        assert reader.ingest_date == ""

    def test_empty_string_ingest_date(self) -> None:
        client = _make_s3_client()
        reader = S3ProcessedReader(client, bucket="my-bucket", ingest_date="")
        assert reader.ingest_date == ""


class TestS3ProcessedReaderReadItems:
    """Requirement 13.3, 13.6: Read JSON files from passed/ prefix."""

    def test_reads_single_item_file(self) -> None:
        item = {"PK": "CITY#Seoul", "SK": "ATTRACTION#001", "province_key": "KR-11"}
        list_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/seoul.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(
            list_responses=[list_resp],
            get_responses={"processed/KR/details/20250115/passed/seoul.json": item},
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        items = reader.read_items()
        assert len(items) == 1
        assert items[0]["PK"] == "CITY#Seoul"

    def test_reads_list_of_items(self) -> None:
        items_data = [
            {"PK": "CITY#Seoul", "SK": "ATTRACTION#001", "province_key": "KR-11"},
            {"PK": "CITY#Seoul", "SK": "ATTRACTION#002", "province_key": "KR-11"},
        ]
        list_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/seoul.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(
            list_responses=[list_resp],
            get_responses={"processed/KR/details/20250115/passed/seoul.json": items_data},
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items()
        assert len(result) == 2

    def test_reads_records_wrapper_format(self) -> None:
        wrapper = {
            "records": [
                {"PK": "CITY#Busan", "SK": "FESTIVAL#001", "province_key": "KR-26"},
            ]
        }
        list_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/busan.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(
            list_responses=[list_resp],
            get_responses={"processed/KR/details/20250115/passed/busan.json": wrapper},
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items()
        assert len(result) == 1
        assert result[0]["PK"] == "CITY#Busan"

    def test_skips_non_json_keys(self) -> None:
        list_resp = {
            "Contents": [
                {"Key": "processed/KR/details/20250115/passed/readme.txt"},
                {"Key": "processed/KR/details/20250115/passed/seoul.json"},
            ],
            "IsTruncated": False,
        }
        item = {"PK": "CITY#Seoul", "SK": "META", "province_key": "KR-11"}
        client = _make_s3_client(
            list_responses=[list_resp],
            get_responses={"processed/KR/details/20250115/passed/seoul.json": item},
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items()
        assert len(result) == 1

    def test_empty_bucket_returns_empty_list(self) -> None:
        list_resp = {"Contents": [], "IsTruncated": False}
        client = _make_s3_client(list_responses=[list_resp])
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items()
        assert result == []

    def test_handles_paginated_listing(self) -> None:
        page1 = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/a.json"}],
            "IsTruncated": True,
            "NextContinuationToken": "token1",
        }
        page2 = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/b.json"}],
            "IsTruncated": False,
        }
        items = {
            "processed/KR/details/20250115/passed/a.json": {"PK": "A", "SK": "S1"},
            "processed/KR/details/20250115/passed/b.json": {"PK": "B", "SK": "S2"},
        }
        client = _make_s3_client(
            list_responses=[page1, page2],
            get_responses=items,
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items()
        assert len(result) == 2

    def test_handles_malformed_json_gracefully(self) -> None:
        list_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/bad.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(list_responses=[list_resp])
        # Override get_object to return invalid JSON
        body = MagicMock()
        body.read.return_value = b"not valid json {"
        client.get_object.return_value = {"Body": body}

        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items()
        assert result == []


class TestS3ProcessedReaderProvinceFilter:
    """Requirement 14.3: Filter items by province_key for local-test mode."""

    def test_filters_by_province_id(self) -> None:
        items_data = [
            {"PK": "CITY#Seoul", "SK": "A#001", "province_key": "KR-11"},
            {"PK": "CITY#Busan", "SK": "A#002", "province_key": "KR-26"},
            {"PK": "CITY#Suwon", "SK": "A#003", "province_key": "KR-41"},
        ]
        list_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/all.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(
            list_responses=[list_resp],
            get_responses={"processed/KR/details/20250115/passed/all.json": items_data},
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items(province_id="KR-26")
        assert len(result) == 1
        assert result[0]["province_key"] == "KR-26"

    def test_no_matching_province_returns_empty(self) -> None:
        items_data = [
            {"PK": "CITY#Seoul", "SK": "A#001", "province_key": "KR-11"},
        ]
        list_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/seoul.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(
            list_responses=[list_resp],
            get_responses={"processed/KR/details/20250115/passed/seoul.json": items_data},
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items(province_id="KR-99")
        assert result == []

    def test_none_province_returns_all(self) -> None:
        items_data = [
            {"PK": "CITY#Seoul", "SK": "A#001", "province_key": "KR-11"},
            {"PK": "CITY#Busan", "SK": "A#002", "province_key": "KR-26"},
        ]
        list_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/multi.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(
            list_responses=[list_resp],
            get_responses={"processed/KR/details/20250115/passed/multi.json": items_data},
        )
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="20250115")
        result = reader.read_items(province_id=None)
        assert len(result) == 2


class TestS3ProcessedReaderAutoDetectDate:
    """Requirement 13.5: Auto-detect latest ingest date when not provided."""

    def test_picks_latest_date(self) -> None:
        # First call: list dates via CommonPrefixes
        date_list_resp = {
            "CommonPrefixes": [
                {"Prefix": "processed/KR/details/20250110/"},
                {"Prefix": "processed/KR/details/20250115/"},
                {"Prefix": "processed/KR/details/20250112/"},
            ],
            "IsTruncated": False,
        }
        # Second call: list files under latest date
        files_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/city.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(list_responses=[date_list_resp, files_resp])
        item = {"PK": "CITY#Test", "SK": "META"}
        body = MagicMock()
        body.read.return_value = json.dumps(item).encode()
        client.get_object.return_value = {"Body": body}

        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date=None)
        result = reader.read_items()

        # Should have auto-detected 20250115 as latest
        assert reader.ingest_date == "20250115"
        assert len(result) == 1

    def test_no_dates_available_returns_empty(self) -> None:
        date_list_resp = {
            "CommonPrefixes": [],
            "IsTruncated": False,
        }
        client = _make_s3_client(list_responses=[date_list_resp])
        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date=None)
        result = reader.read_items()
        assert result == []

    def test_ignores_non_date_prefixes(self) -> None:
        date_list_resp = {
            "CommonPrefixes": [
                {"Prefix": "processed/KR/details/metadata/"},
                {"Prefix": "processed/KR/details/20250115/"},
                {"Prefix": "processed/KR/details/abc/"},
            ],
            "IsTruncated": False,
        }
        files_resp = {
            "Contents": [{"Key": "processed/KR/details/20250115/passed/x.json"}],
            "IsTruncated": False,
        }
        client = _make_s3_client(list_responses=[date_list_resp, files_resp])
        item = {"PK": "CITY#X", "SK": "META"}
        body = MagicMock()
        body.read.return_value = json.dumps(item).encode()
        client.get_object.return_value = {"Body": body}

        reader = S3ProcessedReader(client, bucket="test-bucket", ingest_date="")
        result = reader.read_items()
        assert reader.ingest_date == "20250115"
        assert len(result) == 1
