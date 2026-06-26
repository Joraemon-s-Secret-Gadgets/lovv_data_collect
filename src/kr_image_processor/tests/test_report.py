"""Unit tests for kr_image_processor.report — execution report generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from kr_image_processor.report import generate_report


def _make_s3_client() -> MagicMock:
    """Create a mock S3 client."""
    return MagicMock()


class TestGenerateReport:
    """Tests for generate_report function."""

    def test_basic_report_generation(self):
        """Generates report with correct aggregated stats."""
        s3_client = _make_s3_client()

        execution_context = {
            "image_results": [
                {
                    "city_name_en": "Seoul",
                    "total_records": 10,
                    "images_downloaded": 7,
                    "images_failed": 2,
                    "no_source_image": 1,
                    "review_count": 3,
                },
                {
                    "city_name_en": "Busan",
                    "total_records": 5,
                    "images_downloaded": 4,
                    "images_failed": 0,
                    "no_source_image": 1,
                    "review_count": 1,
                },
            ],
            "load_results": {"loaded": 15, "failed": 0},
            "vector_results": {"manifest": {"upserted": 15, "skipped": 0, "errors": 0}},
            "start_time": datetime.now(timezone.utc).isoformat(),
            "failure_info": None,
        }

        result = generate_report(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            execution_context=execution_context,
        )

        assert result["ingest_date"] == "20260625"
        assert result["summary"]["total_cities"] == 2
        assert result["summary"]["images_downloaded"] == 11
        assert result["summary"]["images_failed"] == 2
        assert result["summary"]["review_count"] == 4
        assert result["summary"]["records_loaded"] == 15
        assert result["summary"]["vectors_built"] == 15
        assert result["status"] == "partial"  # has failed/review items

    def test_per_city_breakdown(self):
        """Report includes per-city breakdown."""
        s3_client = _make_s3_client()

        execution_context = {
            "image_results": [
                {
                    "city_name_en": "Seoul",
                    "total_records": 10,
                    "images_downloaded": 10,
                    "images_failed": 0,
                    "no_source_image": 0,
                    "review_count": 0,
                },
            ],
            "load_results": {"loaded": 10},
            "vector_results": {"manifest": {"upserted": 10}},
            "start_time": datetime.now(timezone.utc).isoformat(),
            "failure_info": None,
        }

        result = generate_report(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            execution_context=execution_context,
        )

        assert len(result["per_city"]) == 1
        assert result["per_city"][0]["city_name_en"] == "Seoul"
        assert result["per_city"][0]["images_ok"] == 10
        assert result["per_city"][0]["images_failed"] == 0
        assert result["per_city"][0]["records_loaded"] == 10

    def test_failure_info_included(self):
        """When pipeline failed, failure_info is included and status is 'failed'."""
        s3_client = _make_s3_client()

        failure_info = {
            "stage": "LoadStage",
            "error": "DynamoDB throttle",
            "items_before_failure": 50,
        }

        execution_context = {
            "image_results": [
                {
                    "city_name_en": "Seoul",
                    "total_records": 10,
                    "images_downloaded": 10,
                    "images_failed": 0,
                    "no_source_image": 0,
                    "review_count": 0,
                },
            ],
            "load_results": None,
            "vector_results": None,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "failure_info": failure_info,
        }

        result = generate_report(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            execution_context=execution_context,
        )

        assert result["status"] == "failed"
        assert result["failure_info"] == failure_info

    def test_s3_output_key(self):
        """Report is written to correct S3 path."""
        s3_client = _make_s3_client()

        execution_context = {
            "image_results": [],
            "load_results": None,
            "vector_results": None,
            "start_time": "",
            "failure_info": None,
        }

        generate_report(
            s3_client=s3_client,
            bucket="my-bucket",
            ingest_date="20260701",
            execution_context=execution_context,
        )

        call_kwargs = s3_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "my-bucket"
        assert call_kwargs["Key"] == "processed/KR/reports/20260701/pipeline_report.json"
        assert call_kwargs["ContentType"] == "application/json"

    def test_empty_image_results(self):
        """Handles empty image_results gracefully."""
        s3_client = _make_s3_client()

        execution_context = {
            "image_results": [],
            "load_results": {},
            "vector_results": {},
            "start_time": "",
            "failure_info": None,
        }

        result = generate_report(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            execution_context=execution_context,
        )

        assert result["summary"]["total_cities"] == 0
        assert result["summary"]["images_downloaded"] == 0
        assert result["per_city"] == []
        assert result["status"] == "success"

    def test_report_has_all_required_fields(self):
        """Report contains all fields specified in the design doc."""
        s3_client = _make_s3_client()

        execution_context = {
            "image_results": [
                {
                    "city_name_en": "Seoul",
                    "total_records": 5,
                    "images_downloaded": 3,
                    "images_failed": 1,
                    "no_source_image": 1,
                    "review_count": 2,
                }
            ],
            "load_results": {"loaded": 5},
            "vector_results": {"manifest": {"upserted": 5}},
            "start_time": "2026-06-25T10:00:00+00:00",
            "failure_info": None,
        }

        result = generate_report(
            s3_client=s3_client,
            bucket="test-bucket",
            ingest_date="20260625",
            execution_context=execution_context,
        )

        # Top-level fields
        assert "ingest_date" in result
        assert "status" in result
        assert "started_at" in result
        assert "completed_at" in result
        assert "total_execution_time_seconds" in result
        assert "summary" in result
        assert "per_city" in result
        assert "failure_info" in result

        # Summary fields
        summary = result["summary"]
        assert "total_cities" in summary
        assert "images_downloaded" in summary
        assert "images_failed" in summary
        assert "review_count" in summary
        assert "records_loaded" in summary
        assert "vectors_built" in summary
