from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestExecuteLoadPhase:
    def test_missing_bucket_returns_error(self) -> None:
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
        from kr_unified_pipeline.handlers import pipeline_handler

        mock_boto3 = MagicMock()
        mock_reader_instance = MagicMock()
        mock_reader_instance.read_items.return_value = [
            {"PK": "CITY#seoul", "SK": "METADATA#city"},
            {"PK": "CITY#busan", "SK": "METADATA#city"},
        ]
        mock_reader_instance.ingest_date = "20250101"

        with patch("kr_unified_pipeline.s3_reader.S3ProcessedReader", return_value=mock_reader_instance):
            with patch("kr_details_pipeline.load._write_item") as mock_write_item:
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
        assert mock_write_item.call_count == 2
