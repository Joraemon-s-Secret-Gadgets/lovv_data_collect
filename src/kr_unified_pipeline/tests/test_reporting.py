"""
Unit tests for the pipeline reporting module.

Tests report generation, console formatting, JSON file output,
error categorization, review reason counts, and verbose mode.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kr_unified_pipeline.models import (
    CityRecord,
    ImageSource,
    PipelineConfig,
    PipelineContext,
    ReviewEntry,
    StageResult,
)
from kr_unified_pipeline.reporting import (
    format_console_report,
    generate_report,
    write_report_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    *,
    num_records: int = 3,
    num_stages: int = 2,
    review_entries: list[ReviewEntry] | None = None,
    errors: list[str] | None = None,
    stage_errors: list[list[str]] | None = None,
) -> PipelineContext:
    """Helper to build a PipelineContext with controllable content."""
    records = []
    for i in range(num_records):
        records.append(
            CityRecord(
                city_id=f"city-{i:03d}",
                city_name_ko=f"도시{i}",
                prefecture_id=f"KR-{i:02d}",
                latitude=37.0 + i if i % 2 == 0 else None,
                longitude=127.0 + i if i % 2 == 0 else None,
                description=f"Description {i}" if i % 3 != 0 else "",
                data_confidence="high" if i % 2 == 0 else "low",
                image_url=f"https://example.com/img{i}.jpg" if i % 2 == 0 else None,
                image_urls=[ImageSource(url=f"https://example.com/img{i}.jpg", source="wikipedia")]
                if i % 2 == 0
                else [],
                field_status={"coordinates": "needs_review"} if i % 2 != 0 else {},
            )
        )

    stage_results = []
    stage_names = ["wikipedia", "tourapi-region", "tourapi-detail"]
    for j in range(num_stages):
        sr = StageResult(
            stage_name=stage_names[j % len(stage_names)],
            started_at=f"2024-01-01T0{j}:00:00+00:00",
            completed_at=f"2024-01-01T0{j}:05:00+00:00",
            records_processed=num_records,
            records_updated=num_records // 2,
            images_collected=j + 1,
            errors=stage_errors[j] if stage_errors and j < len(stage_errors) else [],
        )
        stage_results.append(sr)

    return PipelineContext(
        city_records=records,
        stage_results=stage_results,
        errors=errors or [],
        config=PipelineConfig(verbose=True),
        start_time="2024-01-01T00:00:00+00:00",
        review_manifest=review_entries or [],
    )


# ---------------------------------------------------------------------------
# Tests: generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Tests for generate_report function."""

    def test_basic_summary_metrics(self) -> None:
        """Requirement 8.1: summary contains total records, images, review count."""
        ctx = _make_context(num_records=5, num_stages=2)
        report = generate_report(ctx)

        assert report["summary"]["total_records_processed"] == 5
        assert report["summary"]["total_images_collected"] == 3  # stage 0: 1 + stage 1: 2
        assert report["summary"]["records_transitioned_to_review"] == 0
        assert report["summary"]["total_errors"] == 0

    def test_stage_timestamps_included(self) -> None:
        """Requirement 8.2: Each stage has start/completion timestamps."""
        ctx = _make_context(num_stages=2)
        report = generate_report(ctx)

        assert len(report["stages"]) == 2
        for stage in report["stages"]:
            assert "started_at" in stage
            assert "completed_at" in stage
            assert stage["started_at"] != ""
            assert stage["completed_at"] != ""

    def test_review_reason_counts(self) -> None:
        """Requirement 8.3: Count of records per review_reason category."""
        entries = [
            ReviewEntry(city_id="c1", review_reason="missing_coordinates"),
            ReviewEntry(city_id="c2", review_reason="missing_coordinates"),
            ReviewEntry(city_id="c3", review_reason="empty_description"),
            ReviewEntry(city_id="c4", review_reason="no_image_url"),
        ]
        ctx = _make_context(review_entries=entries)
        report = generate_report(ctx)

        assert report["review_reason_counts"] == {
            "missing_coordinates": 2,
            "empty_description": 1,
            "no_image_url": 1,
        }
        assert report["summary"]["records_transitioned_to_review"] == 4

    def test_error_categorization_api(self) -> None:
        """Requirement 8.4: API errors are categorized correctly."""
        ctx = _make_context(errors=["API status code 429 for city-001"])
        report = generate_report(ctx)

        assert len(report["errors"]["api_errors"]) == 1
        assert "city-001" in report["errors"]["api_errors"][0]

    def test_error_categorization_network(self) -> None:
        """Requirement 8.4: Network failures are categorized correctly."""
        ctx = _make_context(errors=["Connection timeout for city-002"])
        report = generate_report(ctx)

        assert len(report["errors"]["network_errors"]) == 1
        assert "city-002" in report["errors"]["network_errors"][0]

    def test_error_categorization_parsing(self) -> None:
        """Requirement 8.4: Parsing errors are categorized correctly."""
        ctx = _make_context(errors=["JSON decode error for city-003"])
        report = generate_report(ctx)

        assert len(report["errors"]["parsing_errors"]) == 1
        assert "city-003" in report["errors"]["parsing_errors"][0]

    def test_error_categorization_other(self) -> None:
        """Requirement 8.4: Unclassified errors go to other_errors."""
        ctx = _make_context(errors=["Stage 'wikipedia' failed: unknown issue"])
        report = generate_report(ctx)

        assert len(report["errors"]["other_errors"]) == 1

    def test_stage_errors_included_in_categorization(self) -> None:
        """Requirement 8.4: Per-stage errors are also categorized."""
        ctx = _make_context(
            stage_errors=[["API status code 500 for city-010"], ["Connection timeout for city-011"]]
        )
        report = generate_report(ctx)

        assert len(report["errors"]["api_errors"]) == 1
        assert len(report["errors"]["network_errors"]) == 1

    def test_verbose_mode_includes_record_details(self) -> None:
        """Requirement 8.5: Verbose mode outputs per-record details."""
        ctx = _make_context(num_records=2)
        report = generate_report(ctx, verbose=True)

        assert "record_details" in report
        assert len(report["record_details"]) == 2
        detail = report["record_details"][0]
        assert "city_id" in detail
        assert "field_status" in detail
        assert "image_url" in detail
        assert "image_sources" in detail
        assert "data_confidence" in detail

    def test_non_verbose_mode_no_record_details(self) -> None:
        """Without verbose, record_details is not included."""
        ctx = _make_context(num_records=2)
        report = generate_report(ctx, verbose=False)

        assert "record_details" not in report

    def test_empty_context_produces_valid_report(self) -> None:
        """Empty context still produces a valid structured report."""
        ctx = PipelineContext()
        report = generate_report(ctx)

        assert report["summary"]["total_records_processed"] == 0
        assert report["summary"]["total_images_collected"] == 0
        assert report["summary"]["records_transitioned_to_review"] == 0
        assert report["summary"]["total_errors"] == 0
        assert report["stages"] == []
        assert report["review_reason_counts"] == {}

    def test_report_has_timestamps(self) -> None:
        """Report includes pipeline start time and generation timestamp."""
        ctx = _make_context()
        report = generate_report(ctx)

        assert report["pipeline_start_time"] == "2024-01-01T00:00:00+00:00"
        assert "report_generated_at" in report


# ---------------------------------------------------------------------------
# Tests: format_console_report
# ---------------------------------------------------------------------------


class TestFormatConsoleReport:
    """Tests for format_console_report function."""

    def test_contains_header(self) -> None:
        """Console output has report header."""
        ctx = _make_context()
        report = generate_report(ctx)
        output = format_console_report(report)

        assert "PIPELINE EXECUTION REPORT" in output

    def test_contains_summary_metrics(self) -> None:
        """Console output shows summary metrics."""
        ctx = _make_context(num_records=4)
        report = generate_report(ctx)
        output = format_console_report(report)

        assert "Total records processed: 4" in output

    def test_contains_stage_details(self) -> None:
        """Console output shows per-stage information."""
        ctx = _make_context(num_stages=2)
        report = generate_report(ctx)
        output = format_console_report(report)

        assert "[wikipedia]" in output
        assert "Started:" in output
        assert "Completed:" in output

    def test_contains_review_reasons(self) -> None:
        """Console output shows review reason breakdown."""
        entries = [
            ReviewEntry(city_id="c1", review_reason="missing_coordinates"),
            ReviewEntry(city_id="c2", review_reason="empty_description"),
        ]
        ctx = _make_context(review_entries=entries)
        report = generate_report(ctx)
        output = format_console_report(report)

        assert "Review Reasons:" in output
        assert "missing_coordinates: 1" in output
        assert "empty_description: 1" in output

    def test_contains_error_section(self) -> None:
        """Console output shows categorized errors."""
        ctx = _make_context(errors=["API status code 500 for city-099"])
        report = generate_report(ctx)
        output = format_console_report(report)

        assert "API errors" in output
        assert "city-099" in output

    def test_verbose_shows_per_record(self) -> None:
        """Console output shows per-record details in verbose mode."""
        ctx = _make_context(num_records=2)
        report = generate_report(ctx, verbose=True)
        output = format_console_report(report)

        assert "Per-Record Details:" in output
        assert "city-000" in output

    def test_empty_report_no_crash(self) -> None:
        """Formatting an empty report does not crash."""
        report = generate_report(PipelineContext())
        output = format_console_report(report)

        assert "PIPELINE EXECUTION REPORT" in output
        assert "Total records processed: 0" in output


# ---------------------------------------------------------------------------
# Tests: write_report_file
# ---------------------------------------------------------------------------


class TestWriteReportFile:
    """Tests for write_report_file function."""

    @pytest.fixture
    def report_dir(self) -> Path:
        """Create a temp directory within the project for report tests."""
        import shutil
        import tempfile

        d = Path(tempfile.mkdtemp(prefix="report_test_", dir="."))
        yield d
        shutil.rmtree(d, ignore_errors=True)

    def test_writes_json_file(self, report_dir: Path) -> None:
        """Report is written as valid JSON."""
        ctx = _make_context(num_records=2)
        report = generate_report(ctx)
        filepath = write_report_file(report, report_dir)

        assert filepath.exists()
        assert filepath.suffix == ".json"

        content = json.loads(filepath.read_text(encoding="utf-8"))
        assert content["summary"]["total_records_processed"] == 2

    def test_creates_directory_if_missing(self, report_dir: Path) -> None:
        """Output directory is created if it doesn't exist."""
        nested = report_dir / "reports" / "sub"
        ctx = _make_context()
        report = generate_report(ctx)
        filepath = write_report_file(report, nested)

        assert nested.exists()
        assert filepath.exists()

    def test_filename_contains_timestamp(self, report_dir: Path) -> None:
        """Report filename includes a timestamp."""
        report = generate_report(PipelineContext())
        filepath = write_report_file(report, report_dir)

        assert filepath.name.startswith("pipeline_report_")
        assert filepath.name.endswith(".json")

    def test_report_preserves_unicode(self, report_dir: Path) -> None:
        """Korean characters in city names are preserved."""
        ctx = _make_context(num_records=1)
        report = generate_report(ctx, verbose=True)
        filepath = write_report_file(report, report_dir)

        content = filepath.read_text(encoding="utf-8")
        assert "도시0" in content
