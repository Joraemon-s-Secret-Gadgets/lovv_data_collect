"""Unit tests for kr_image_processor.handlers.image_handler — command routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from kr_image_processor.handlers.image_handler import handler


class TestHandlerRouting:
    """Tests for handler command dispatch."""

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    @patch("kr_image_processor.handlers.image_handler._handle_process_city")
    def test_default_command_is_process_city(self, mock_handle, mock_s3):
        """When no command specified, defaults to process_city."""
        mock_handle.return_value = {"statusCode": 200}

        event = {
            "bucket": "test-bucket",
            "image_bucket": "img-bucket",
            "ingest_date": "20260625",
            "city_name_en": "Seoul",
            "source_key": "path/to/file.json",
        }

        result = handler(event, None)

        mock_handle.assert_called_once_with(event)
        assert result["statusCode"] == 200

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    @patch("kr_image_processor.handlers.image_handler._handle_aggregate_review")
    def test_aggregate_review_command(self, mock_handle, mock_s3):
        """Routes aggregate_review command correctly."""
        mock_handle.return_value = {"statusCode": 200, "total_review": 5}

        event = {
            "command": "aggregate_review",
            "bucket": "test-bucket",
            "ingest_date": "20260625",
            "image_results": [],
        }

        result = handler(event, None)

        mock_handle.assert_called_once_with(event)
        assert result["statusCode"] == 200

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    @patch("kr_image_processor.handlers.image_handler._handle_generate_report")
    def test_generate_report_command(self, mock_handle, mock_s3):
        """Routes generate_report command correctly."""
        mock_handle.return_value = {"statusCode": 200, "status": "success"}

        event = {
            "command": "generate_report",
            "bucket": "test-bucket",
            "ingest_date": "20260625",
            "execution_context": {},
        }

        result = handler(event, None)

        mock_handle.assert_called_once_with(event)
        assert result["statusCode"] == 200

    def test_unknown_command_returns_400(self):
        """Unknown commands return 400 error."""
        event = {"command": "invalid_command"}

        result = handler(event, None)

        assert result["statusCode"] == 400
        assert "Unknown command" in result["error"]
        assert "invalid_command" in result["error"]

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_missing_bucket_returns_400(self, mock_s3):
        """Missing bucket param returns descriptive error."""
        event = {
            "command": "process_city",
            "ingest_date": "20260625",
            "city_name_en": "Seoul",
            "source_key": "path/to/file.json",
        }

        result = handler(event, None)

        assert result["statusCode"] == 400
        assert "bucket" in result["error"].lower()

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_missing_ingest_date_returns_400(self, mock_s3):
        """Missing ingest_date returns descriptive error."""
        event = {
            "command": "process_city",
            "bucket": "test-bucket",
            "image_bucket": "img-bucket",
            "city_name_en": "Seoul",
            "source_key": "path/to/file.json",
        }

        result = handler(event, None)

        assert result["statusCode"] == 400
        assert "ingest_date" in result["error"].lower()

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_missing_city_name_returns_400(self, mock_s3):
        """Missing city_name_en returns descriptive error for process_city."""
        event = {
            "command": "process_city",
            "bucket": "test-bucket",
            "image_bucket": "img-bucket",
            "ingest_date": "20260625",
            "source_key": "path/to/file.json",
        }

        result = handler(event, None)

        assert result["statusCode"] == 400
        assert "city_name_en" in result["error"].lower()

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_missing_image_bucket_returns_400(self, mock_s3):
        """Missing image_bucket returns descriptive error for process_city."""
        event = {
            "command": "process_city",
            "bucket": "test-bucket",
            "ingest_date": "20260625",
            "city_name_en": "Seoul",
            "source_key": "path/to/file.json",
        }

        result = handler(event, None)

        assert result["statusCode"] == 400
        assert "image_bucket" in result["error"].lower()

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_exception_returns_500(self, mock_s3):
        """Unhandled exceptions return 500 with error message."""
        mock_s3.return_value = MagicMock()

        # Patch process_city to raise an exception
        with patch(
            "kr_image_processor.processor.process_city",
            side_effect=RuntimeError("S3 connection failed"),
        ):
            event = {
                "command": "process_city",
                "bucket": "test-bucket",
                "image_bucket": "img-bucket",
                "ingest_date": "20260625",
                "city_name_en": "Seoul",
                "source_key": "path/to/file.json",
            }

            result = handler(event, None)

            assert result["statusCode"] == 500
            assert "S3 connection failed" in result["error"]

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_aggregate_review_missing_bucket(self, mock_s3):
        """aggregate_review with missing bucket returns 400."""
        event = {
            "command": "aggregate_review",
            "ingest_date": "20260625",
            "image_results": [],
        }

        result = handler(event, None)

        assert result["statusCode"] == 400
        assert "bucket" in result["error"].lower()

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_generate_report_missing_bucket(self, mock_s3):
        """generate_report with missing bucket returns 400."""
        event = {
            "command": "generate_report",
            "ingest_date": "20260625",
            "execution_context": {},
        }

        result = handler(event, None)

        assert result["statusCode"] == 400
        assert "bucket" in result["error"].lower()

    @patch("kr_image_processor.handlers.image_handler._get_s3_client")
    def test_env_vars_used_as_fallback(self, mock_s3):
        """Environment variables are used when event params are missing."""
        import os

        mock_s3.return_value = MagicMock()

        with patch.dict(os.environ, {"PIPELINE_BUCKET": "env-bucket", "IMAGE_BUCKET": "env-img"}):
            with patch(
                "kr_image_processor.review.aggregate_review",
                return_value={"total_review": 0, "review_by_reason": {}},
            ):
                event = {
                    "command": "aggregate_review",
                    "ingest_date": "20260625",
                    "image_results": [],
                }

                result = handler(event, None)

                assert result["statusCode"] == 200
