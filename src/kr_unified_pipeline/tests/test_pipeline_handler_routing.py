from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


class TestHandlerCommandRouting:
    def test_unsupported_command_returns_400(self) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        result = handler({"command": "unknown"}, None)

        assert result["statusCode"] == 400
        assert "Unsupported command" in result["error"]

    def test_empty_command_returns_400(self) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        result = handler({}, None)

        assert result["statusCode"] == 400
        assert "error" in result

    def test_vector_build_command_returns_400(self) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        result = handler({"command": "vector-build"}, None)

        assert result["statusCode"] == 400
        assert "vector-build" in result["error"]

    def test_e2e_command_returns_400(self) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        result = handler({"command": "e2e", "bucket": "test-bucket"}, None)

        assert result["statusCode"] == 400
        assert "e2e" in result["error"]

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_load_command_calls_load_phase(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {
                "s3_files_read": 5,
                "loaded": 5,
                "load_failed": 0,
                "ingest_date": "20250101",
                "failures": [],
            },
            [],
        )

        result = handler({"command": "load", "bucket": "test-bucket"}, None)

        assert result["statusCode"] == 200
        mock_load.assert_called_once()
        assert result["summary"]["records_loaded"] == 5


class TestHandlerConfigResolution:
    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_table_name_from_event(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {
                "s3_files_read": 1,
                "loaded": 1,
                "load_failed": 0,
                "ingest_date": "20250101",
                "failures": [],
            },
            [],
        )

        with patch.dict(os.environ, {"DYNAMODB_TABLE": "EnvTable"}):
            handler({"command": "load", "table_name": "EventTable", "bucket": "b"}, None)

        call_kwargs = mock_load.call_args[1]
        assert call_kwargs["table_name"] == "EventTable"

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_table_name_from_env(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {
                "s3_files_read": 1,
                "loaded": 1,
                "load_failed": 0,
                "ingest_date": "20250101",
                "failures": [],
            },
            [],
        )

        with patch.dict(os.environ, {"DYNAMODB_TABLE": "EnvTable"}, clear=False):
            handler({"command": "load", "bucket": "b"}, None)

        call_kwargs = mock_load.call_args[1]
        assert call_kwargs["table_name"] == "EnvTable"

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_default_table_name(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {
                "s3_files_read": 1,
                "loaded": 1,
                "load_failed": 0,
                "ingest_date": "20250101",
                "failures": [],
            },
            [],
        )

        env = {k: v for k, v in os.environ.items() if k != "DYNAMODB_TABLE"}
        with patch.dict(os.environ, env, clear=True):
            handler({"command": "load", "bucket": "b"}, None)

        call_kwargs = mock_load.call_args[1]
        assert call_kwargs["table_name"] == "TourKoreaDomainDataV2"


class TestHandlerErrorHandling:
    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_load_phase_failure_returns_207(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (None, ["Non-recoverable error: connection refused"])

        result = handler({"command": "load", "bucket": "b"}, None)

        assert result["statusCode"] == 207
        assert result["summary"]["load"] is None
        assert len(result["summary"]["errors"]) > 0

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_partial_load_failure_returns_207(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {
                "s3_files_read": 10,
                "loaded": 8,
                "load_failed": 2,
                "ingest_date": "20250101",
                "failures": [],
            },
            ["item1 failed", "item2 failed"],
        )

        result = handler({"command": "load", "bucket": "b"}, None)

        assert result["statusCode"] == 207
        assert result["summary"]["records_loaded"] == 8


class TestHandlerSummaryReport:
    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_summary_contains_loader_fields_only(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {
                "s3_files_read": 20,
                "loaded": 18,
                "load_failed": 2,
                "ingest_date": "20250115",
                "failures": [],
            },
            [],
        )

        result = handler({"command": "load", "bucket": "test-bucket", "ingest_date": "20250115"}, None)

        summary = result["summary"]
        assert summary["s3_files_read"] == 20
        assert summary["records_loaded"] == 18
        assert summary["execution_time_seconds"] >= 0
        assert "vector" not in summary
        assert "vectors_upserted" not in summary

    @patch("kr_unified_pipeline.handlers.pipeline_handler._execute_load_phase")
    def test_summary_preserves_loader_config(self, mock_load: MagicMock) -> None:
        from kr_unified_pipeline.handlers.pipeline_handler import handler

        mock_load.return_value = (
            {
                "s3_files_read": 1,
                "loaded": 1,
                "load_failed": 0,
                "ingest_date": "20250101",
                "failures": [],
            },
            [],
        )

        result = handler(
            {
                "command": "load",
                "bucket": "my-bucket",
                "ingest_date": "20250101",
                "province_id": "KR-42",
            },
            None,
        )

        summary = result["summary"]
        assert summary["command"] == "load"
        assert summary["bucket"] == "my-bucket"
        assert summary["ingest_date"] == "20250101"
        assert summary["province_id"] == "KR-42"
        assert "vector_bucket" not in summary
        assert "index_name" not in summary
        assert "rebuild_mode" not in summary
