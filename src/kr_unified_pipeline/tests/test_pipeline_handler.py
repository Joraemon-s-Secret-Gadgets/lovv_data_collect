"""Unit tests for pipeline_handler event routing logic.

Tests cover:
- Command routing (load, vector-build, e2e, invalid)
- Config reading from event fields and env vars
- Graceful error handling when phases fail
- Summary report structure

Requirements: 13.2, 13.3, 13.4, 13.5, 13.7, 13.8, 13.9
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
from typing import Any

import pytest


class TestHandlerCommandRouting:
    """Test that the handler routes commands correctly."""

    def test_unsupported_command_returns_400(self) -> None:
        """Unknown command returns statusCode 400 with error message."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        result = handler({"command": "unknown"}, None)

        assert result["statusCode"] == 400
        assert "Unsupported command" in result["error"]

    def test_empty_command_returns_400(self) -> None:
        """Empty/missing command returns statusCode 400."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        result = handler({}, None)

        assert result["statusCode"] == 400
        assert "error" in result

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_load_command_calls_load_phase(self, mock_load: MagicMock) -> None:
        """'load' command invokes the load phase only."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 5, "loaded": 5, "load_failed": 0, "ingest_date": "20250101", "failures": []},
            [],
        )

        result = handler({"command": "load", "bucket": "test-bucket"}, None)

        assert result["statusCode"] == 200
        mock_load.assert_called_once()
        assert result["summary"]["records_loaded"] == 5

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_vector_build_phase")
    def test_vector_build_command_calls_vector_phase(self, mock_vector: MagicMock) -> None:
        """'vector-build' command invokes the vector phase only."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_vector.return_value = (
            {"items_exported": 10, "chunks_created": 10, "items_upserted": 10, "items_skipped": 0, "rebuild_mode": "full"},
            [],
        )

        result = handler({"command": "vector-build"}, None)

        assert result["statusCode"] == 200
        mock_vector.assert_called_once()
        assert result["summary"]["vectors_upserted"] == 10

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_vector_build_phase")
    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_e2e_command_calls_both_phases(
        self, mock_load: MagicMock, mock_vector: MagicMock
    ) -> None:
        """'e2e' command invokes load then vector-build."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 3, "loaded": 3, "load_failed": 0, "ingest_date": "20250115", "failures": []},
            [],
        )
        mock_vector.return_value = (
            {"items_exported": 3, "chunks_created": 3, "items_upserted": 3, "items_skipped": 0, "rebuild_mode": "full"},
            [],
        )

        result = handler({"command": "e2e", "bucket": "test-bucket"}, None)

        assert result["statusCode"] == 200
        mock_load.assert_called_once()
        mock_vector.assert_called_once()
        assert result["summary"]["records_loaded"] == 3
        assert result["summary"]["vectors_upserted"] == 3


class TestHandlerConfigResolution:
    """Test that config is read from event fields and env vars correctly."""

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_table_name_from_event(self, mock_load: MagicMock) -> None:
        """table_name in event overrides env var."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 1, "loaded": 1, "load_failed": 0, "ingest_date": "20250101", "failures": []},
            [],
        )

        with patch.dict(os.environ, {"DYNAMODB_TABLE": "EnvTable"}):
            result = handler({"command": "load", "table_name": "EventTable", "bucket": "b"}, None)

        # Verify the event value was passed to _execute_load_phase
        call_kwargs = mock_load.call_args[1]
        assert call_kwargs["table_name"] == "EventTable"

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_table_name_from_env(self, mock_load: MagicMock) -> None:
        """DYNAMODB_TABLE env var used when event field is absent."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 1, "loaded": 1, "load_failed": 0, "ingest_date": "20250101", "failures": []},
            [],
        )

        with patch.dict(os.environ, {"DYNAMODB_TABLE": "EnvTable"}, clear=False):
            result = handler({"command": "load", "bucket": "b"}, None)

        call_kwargs = mock_load.call_args[1]
        assert call_kwargs["table_name"] == "EnvTable"

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_default_table_name(self, mock_load: MagicMock) -> None:
        """Default table name is TourKoreaDomainDataV2."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 1, "loaded": 1, "load_failed": 0, "ingest_date": "20250101", "failures": []},
            [],
        )

        env = {k: v for k, v in os.environ.items() if k != "DYNAMODB_TABLE"}
        with patch.dict(os.environ, env, clear=True):
            result = handler({"command": "load", "bucket": "b"}, None)

        call_kwargs = mock_load.call_args[1]
        assert call_kwargs["table_name"] == "TourKoreaDomainDataV2"

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_vector_build_phase")
    def test_vector_config_from_env(self, mock_vector: MagicMock) -> None:
        """VECTOR_BUCKET and VECTOR_INDEX env vars are used."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_vector.return_value = (
            {"items_exported": 1, "chunks_created": 1, "items_upserted": 1, "items_skipped": 0, "rebuild_mode": "full"},
            [],
        )

        with patch.dict(os.environ, {"VECTOR_BUCKET": "my-vec-bucket", "VECTOR_INDEX": "my-index"}):
            result = handler({"command": "vector-build"}, None)

        call_kwargs = mock_vector.call_args[1]
        assert call_kwargs["vector_bucket"] == "my-vec-bucket"
        assert call_kwargs["index_name"] == "my-index"


class TestHandlerErrorHandling:
    """Test graceful error handling when phases fail."""

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_load_phase_failure_returns_207(self, mock_load: MagicMock) -> None:
        """Non-recoverable load failure returns statusCode 207."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (None, ["Non-recoverable error: connection refused"])

        result = handler({"command": "load", "bucket": "b"}, None)

        assert result["statusCode"] == 207
        assert result["summary"]["load"] is None
        assert len(result["summary"]["errors"]) > 0

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_vector_build_phase")
    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_e2e_load_failure_skips_vector(
        self, mock_load: MagicMock, mock_vector: MagicMock
    ) -> None:
        """In e2e mode, if load fails, vector-build is skipped (Req 13.8)."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (None, ["Load failed"])

        result = handler({"command": "e2e", "bucket": "b"}, None)

        assert result["statusCode"] == 207
        mock_vector.assert_not_called()
        assert "skipped" in result["summary"]["errors"][-1].lower()

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_partial_load_failure_returns_207(self, mock_load: MagicMock) -> None:
        """Some items failing to load returns statusCode 207."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 10, "loaded": 8, "load_failed": 2, "ingest_date": "20250101", "failures": []},
            ["item1 failed", "item2 failed"],
        )

        result = handler({"command": "load", "bucket": "b"}, None)

        assert result["statusCode"] == 207
        assert result["summary"]["records_loaded"] == 8

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_vector_build_phase")
    def test_vector_phase_failure_returns_207(self, mock_vector: MagicMock) -> None:
        """Non-recoverable vector build failure returns statusCode 207."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_vector.return_value = (None, ["Bedrock connection error"])

        result = handler({"command": "vector-build"}, None)

        assert result["statusCode"] == 207
        assert result["summary"]["vector"] is None


class TestHandlerSummaryReport:
    """Test the combined summary report structure."""

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_vector_build_phase")
    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_summary_contains_all_required_fields(
        self, mock_load: MagicMock, mock_vector: MagicMock
    ) -> None:
        """Summary report includes S3 files read, records loaded, vectors upserted, execution time."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 20, "loaded": 18, "load_failed": 2, "ingest_date": "20250115", "failures": []},
            [],
        )
        mock_vector.return_value = (
            {"items_exported": 18, "chunks_created": 25, "items_upserted": 25, "items_skipped": 0, "rebuild_mode": "full"},
            [],
        )

        result = handler({"command": "e2e", "bucket": "test-bucket", "ingest_date": "20250115"}, None)

        summary = result["summary"]
        # Requirement 13.9: combined summary report
        assert "s3_files_read" in summary
        assert "records_loaded" in summary
        assert "vectors_upserted" in summary
        assert "execution_time_seconds" in summary
        assert summary["s3_files_read"] == 20
        assert summary["records_loaded"] == 18
        assert summary["vectors_upserted"] == 25
        assert summary["execution_time_seconds"] >= 0

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_summary_preserves_config(self, mock_load: MagicMock) -> None:
        """Summary includes the configuration used for traceability."""
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {"s3_files_read": 1, "loaded": 1, "load_failed": 0, "ingest_date": "20250101", "failures": []},
            [],
        )

        result = handler({
            "command": "load",
            "bucket": "my-bucket",
            "ingest_date": "20250101",
            "province_id": "KR-42",
        }, None)

        summary = result["summary"]
        assert summary["command"] == "load"
        assert summary["bucket"] == "my-bucket"
        assert summary["ingest_date"] == "20250101"
        assert summary["province_id"] == "KR-42"


class TestExecuteLoadPhase:
    """Test the _execute_load_phase helper directly."""

    def test_missing_bucket_returns_error(self) -> None:
        """Load phase without bucket returns None result with error."""
        from kr_unified_pipeline.handlers.pipeline_handler import _execute_load_phase

        result, errors = _execute_load_phase(
            boto3_module=MagicMock(),
            bucket="",
            ingest_date="20250101",
            table_name="TestTable",
            province_id=None,
        )

        assert result is None
        assert any("bucket" in e.lower() for e in errors)

    def test_successful_load(self) -> None:
        """Successful load returns correct counts."""
        from kr_unified_pipeline.handlers import pipeline_handler

        mock_boto3 = MagicMock()
        mock_reader_instance = MagicMock()
        mock_reader_instance.read_items.return_value = [
            {"PK": "CITY#seoul", "SK": "METADATA#city"},
            {"PK": "CITY#busan", "SK": "METADATA#city"},
        ]
        mock_reader_instance.ingest_date = "20250101"

        with patch("kr_unified_pipeline.s3_reader.S3ProcessedReader", return_value=mock_reader_instance):
            with patch("kr_details_pipeline.load._write_item") as mock_wr:
                result, errors = pipeline_handler._execute_load_phase(
                    boto3_module=mock_boto3,
                    bucket="test-bucket",
                    ingest_date="20250101",
                    table_name="TestTable",
                    province_id=None,
                )

        assert result is not None
        assert result["loaded"] == 2
        assert result["load_failed"] == 0
        assert errors == []
        assert mock_wr.call_count == 2
