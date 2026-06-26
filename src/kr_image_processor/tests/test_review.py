"""Unit tests for kr_image_processor.review — review manifest aggregation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from kr_image_processor.review import aggregate_review


def _make_s3_client() -> MagicMock:
    """Create a mock S3 client."""
    return MagicMock()


class TestAggregateReview:
    """Tests for aggregate_review function."""

    def test_collects_entries_from_multiple_cities(self):
        """Entries from all cities are combined into a single manifest."""
        s3_client = _make_s3_client()

        image_results = [
            {
                "city_name_en": "Seoul",
                "review_entries": [
                    {
                        "city_name_en": "Seoul",
                        "content_id": "100",
                        "entity_type": "attraction",
                        "original_image_url": "http://cdn.example.com/img.jpg",
                        "failure_reason": "download_failed",
                        "error_message": "404",
                        "timestamp": "2026-06-25T10:00:00Z",
                    }
                ],
            },
            {
                "city_name_en": "Busan",
                "review_entries": [
                    {
                        "city_name_en": "Busan",
                        "content_id": "200",
                        "entity_type": "festival",
                        "original_image_url": "",
                        "failure_reason": "no_source_image",
                        "error_message": "",
                        "timestamp": "2026-06-25T10:01:00Z",
                    },
                    {
                        "city_name_en": "Busan",
                        "content_id": "201",
                        "entity_type": "attraction",
                        "original_image_url": "http://cdn.example.com/bad.jpg",
                        "failure_reason": "download_failed",
                        "error_message": "timeout",
                        "timestamp": "2026-06-25T10:02:00Z",
                    },
                ],
            },
        ]

        result = aggregate_review(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            image_results=image_results,
        )

        assert result["total_review"] == 3
        assert result["review_by_reason"] == {
            "download_failed": 2,
            "no_source_image": 1,
        }

        # Verify S3 write
        s3_client.put_object.assert_called_once()
        call_kwargs = s3_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "processed/KR/review/20260625/image_review.json"

        written_entries = json.loads(call_kwargs["Body"].decode("utf-8"))
        assert len(written_entries) == 3

    def test_empty_results(self):
        """No review entries produces empty manifest."""
        s3_client = _make_s3_client()

        image_results = [
            {"city_name_en": "Seoul", "review_entries": []},
            {"city_name_en": "Busan", "review_entries": []},
        ]

        result = aggregate_review(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            image_results=image_results,
        )

        assert result["total_review"] == 0
        assert result["review_by_reason"] == {}

        # Still writes an empty manifest
        s3_client.put_object.assert_called_once()
        call_kwargs = s3_client.put_object.call_args.kwargs
        written_entries = json.loads(call_kwargs["Body"].decode("utf-8"))
        assert written_entries == []

    def test_city_result_without_review_entries_key(self):
        """City results missing review_entries key are handled gracefully."""
        s3_client = _make_s3_client()

        image_results = [
            {"city_name_en": "Seoul", "images_downloaded": 10},
            {
                "city_name_en": "Busan",
                "review_entries": [
                    {
                        "city_name_en": "Busan",
                        "content_id": "300",
                        "entity_type": "attraction",
                        "original_image_url": "",
                        "failure_reason": "no_source_image",
                        "error_message": "",
                        "timestamp": "2026-06-25T10:00:00Z",
                    }
                ],
            },
        ]

        result = aggregate_review(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            image_results=image_results,
        )

        assert result["total_review"] == 1

    def test_s3_key_format(self):
        """S3 key follows the expected path pattern."""
        s3_client = _make_s3_client()

        result = aggregate_review(
            s3_client=s3_client,
            bucket="my-bucket",
            ingest_date="20260701",
            image_results=[],
        )

        call_kwargs = s3_client.put_object.call_args.kwargs
        assert call_kwargs["Key"] == "processed/KR/review/20260701/image_review.json"
        assert call_kwargs["ContentType"] == "application/json"
