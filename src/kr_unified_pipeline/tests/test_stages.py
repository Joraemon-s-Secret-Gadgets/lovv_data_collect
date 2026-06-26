"""Unit tests for pipeline stage wrappers.

Tests verify that WikipediaStage, TourAPIRegionStage, and TourAPIDetailStage
implement the PipelineStage Protocol, handle import failures gracefully,
load existing records when executed independently, and respect province_id
filtering.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from kr_unified_pipeline.models import CityRecord, PipelineConfig, PipelineContext, StageResult
from kr_unified_pipeline.stages import (
    STAGE_ORDER,
    TourAPIDetailStage,
    TourAPIRegionStage,
    WikipediaStage,
    _filter_by_province,
    _load_existing_city_records,
)


@pytest.fixture
def work_dir() -> Path:
    """Create a temporary working directory within the project for tests."""
    base = Path(__file__).resolve().parent / "_test_tmp"
    base.mkdir(parents=True, exist_ok=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# Protocol conformance tests
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify each stage has the required name property and execute method."""

    def test_wikipedia_stage_has_name(self) -> None:
        stage = WikipediaStage()
        assert stage.name == "wikipedia"

    def test_tourapi_region_stage_has_name(self) -> None:
        stage = TourAPIRegionStage()
        assert stage.name == "tourapi-region"

    def test_tourapi_detail_stage_has_name(self) -> None:
        stage = TourAPIDetailStage()
        assert stage.name == "tourapi-detail"

    def test_stage_names_match_stage_order(self) -> None:
        """Each stage name must correspond to an entry in STAGE_ORDER."""
        stages = [WikipediaStage(), TourAPIRegionStage(), TourAPIDetailStage()]
        for stage in stages:
            assert stage.name in STAGE_ORDER

    def test_stages_have_execute_method(self) -> None:
        stages = [WikipediaStage(), TourAPIRegionStage(), TourAPIDetailStage()]
        for stage in stages:
            assert hasattr(stage, "execute")
            assert callable(stage.execute)


# ---------------------------------------------------------------------------
# Graceful fallback tests (import failure)
# ---------------------------------------------------------------------------


class TestGracefulFallback:
    """Verify stages return context unchanged when crawling modules unavailable."""

    def test_wikipedia_stage_returns_context_on_import_failure(self) -> None:
        config = PipelineConfig(output_dir="nonexistent_dir/")
        ctx = PipelineContext(config=config)

        with patch.dict("sys.modules", {"crawling": None, "crawling.KR": None, "crawling.KR.pipeline": None}):
            stage = WikipediaStage()
            result = stage.execute(ctx)

        # Context returned unchanged (no records added)
        assert result.city_records == []
        # Stage result recorded
        assert len(result.stage_results) == 1
        assert result.stage_results[0].stage_name == "wikipedia"
        assert result.stage_results[0].completed_at != ""

    def test_tourapi_region_stage_returns_context_on_import_failure(self) -> None:
        config = PipelineConfig(output_dir="nonexistent_dir/")
        ctx = PipelineContext(config=config)

        with patch.dict("sys.modules", {
            "crawling": None,
            "crawling.KR": None,
            "crawling.KR.tour_api_region_detail_acquisition": None,
        }):
            stage = TourAPIRegionStage()
            result = stage.execute(ctx)

        assert result.city_records == []
        assert len(result.stage_results) == 1
        assert result.stage_results[0].stage_name == "tourapi-region"

    def test_tourapi_detail_stage_returns_context_on_import_failure(self) -> None:
        config = PipelineConfig(output_dir="nonexistent_dir/")
        ctx = PipelineContext(config=config)

        with patch.dict("sys.modules", {
            "crawling": None,
            "crawling.KR": None,
            "crawling.KR.tour_api_detail_harvester": None,
        }):
            stage = TourAPIDetailStage()
            result = stage.execute(ctx)

        assert result.city_records == []
        assert len(result.stage_results) == 1
        assert result.stage_results[0].stage_name == "tourapi-detail"


# ---------------------------------------------------------------------------
# Load existing city records tests
# ---------------------------------------------------------------------------


class TestLoadExistingRecords:
    """Verify _load_existing_city_records helper function."""

    def test_load_from_nonexistent_dir(self) -> None:
        records = _load_existing_city_records("/nonexistent/path/")
        assert records == []

    def test_load_from_valid_cities_json(self, work_dir: Path) -> None:
        cities_data = [
            {
                "city_id": "KR-42-001",
                "city_name_ko": "춘천시",
                "prefecture_id": "KR-42",
                "latitude": 37.88,
                "longitude": 127.73,
                "description": "Test description",
            },
            {
                "city_id": "KR-42-002",
                "city_name_ko": "원주시",
                "prefecture_id": "KR-42",
                "latitude": 37.35,
                "longitude": 127.95,
                "description": "Another city",
            },
        ]
        (work_dir / "cities.json").write_text(
            json.dumps(cities_data, ensure_ascii=False), encoding="utf-8"
        )

        records = _load_existing_city_records(str(work_dir))
        assert len(records) == 2
        assert records[0].city_id == "KR-42-001"
        assert records[0].city_name_ko == "춘천시"
        assert records[1].city_id == "KR-42-002"

    def test_load_from_invalid_json(self, work_dir: Path) -> None:
        (work_dir / "cities.json").write_text("not valid json", encoding="utf-8")
        records = _load_existing_city_records(str(work_dir))
        assert records == []

    def test_load_from_non_list_json(self, work_dir: Path) -> None:
        (work_dir / "cities.json").write_text('{"key": "value"}', encoding="utf-8")
        records = _load_existing_city_records(str(work_dir))
        assert records == []


# ---------------------------------------------------------------------------
# Province filtering tests
# ---------------------------------------------------------------------------


class TestProvinceFiltering:
    """Verify _filter_by_province helper function."""

    def test_filter_with_no_province_id(self) -> None:
        records = [
            CityRecord(city_id="1", prefecture_id="KR-42"),
            CityRecord(city_id="2", prefecture_id="KR-47"),
        ]
        result = _filter_by_province(records, None)
        assert len(result) == 2

    def test_filter_with_matching_province_id(self) -> None:
        records = [
            CityRecord(city_id="1", prefecture_id="KR-42"),
            CityRecord(city_id="2", prefecture_id="KR-47"),
            CityRecord(city_id="3", prefecture_id="KR-42"),
        ]
        result = _filter_by_province(records, "KR-42")
        assert len(result) == 2
        assert all(r.prefecture_id == "KR-42" for r in result)

    def test_filter_with_no_matching_province_id(self) -> None:
        records = [
            CityRecord(city_id="1", prefecture_id="KR-42"),
            CityRecord(city_id="2", prefecture_id="KR-47"),
        ]
        result = _filter_by_province(records, "KR-11")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Independent execution tests (loads existing records)
# ---------------------------------------------------------------------------


class TestIndependentExecution:
    """Verify stages load existing CityRecords when context is empty."""

    def test_wikipedia_stage_loads_existing_records(self, work_dir: Path) -> None:
        cities_data = [
            {"city_id": "KR-42-001", "city_name_ko": "춘천시", "prefecture_id": "KR-42"},
        ]
        (work_dir / "cities.json").write_text(
            json.dumps(cities_data, ensure_ascii=False), encoding="utf-8"
        )

        config = PipelineConfig(output_dir=str(work_dir))
        ctx = PipelineContext(config=config)

        with patch.dict("sys.modules", {"crawling": None, "crawling.KR": None, "crawling.KR.pipeline": None}):
            stage = WikipediaStage()
            result = stage.execute(ctx)

        # Records loaded from existing file even though crawling module unavailable
        assert len(result.city_records) == 1
        assert result.city_records[0].city_id == "KR-42-001"

    def test_tourapi_detail_stage_loads_existing_records(self, work_dir: Path) -> None:
        cities_data = [
            {"city_id": "KR-47-001", "city_name_ko": "포항시", "prefecture_id": "KR-47"},
        ]
        (work_dir / "cities.json").write_text(
            json.dumps(cities_data, ensure_ascii=False), encoding="utf-8"
        )

        config = PipelineConfig(output_dir=str(work_dir))
        ctx = PipelineContext(config=config)

        with patch.dict("sys.modules", {
            "crawling": None,
            "crawling.KR": None,
            "crawling.KR.tour_api_detail_harvester": None,
        }):
            stage = TourAPIDetailStage()
            result = stage.execute(ctx)

        assert len(result.city_records) == 1
        assert result.city_records[0].city_id == "KR-47-001"

    def test_does_not_reload_when_context_has_records(self, work_dir: Path) -> None:
        """If context already has city_records, don't load from disk."""
        # Write different data to disk
        cities_data = [
            {"city_id": "DISK-001", "city_name_ko": "디스크시", "prefecture_id": "KR-11"},
        ]
        (work_dir / "cities.json").write_text(
            json.dumps(cities_data, ensure_ascii=False), encoding="utf-8"
        )

        # Context already has records
        existing = [CityRecord(city_id="CTX-001", city_name_ko="컨텍스트시", prefecture_id="KR-42")]
        config = PipelineConfig(output_dir=str(work_dir))
        ctx = PipelineContext(config=config, city_records=existing)

        with patch.dict("sys.modules", {"crawling": None, "crawling.KR": None, "crawling.KR.pipeline": None}):
            stage = WikipediaStage()
            result = stage.execute(ctx)

        # Should keep context records, not load from disk
        assert len(result.city_records) == 1
        assert result.city_records[0].city_id == "CTX-001"
