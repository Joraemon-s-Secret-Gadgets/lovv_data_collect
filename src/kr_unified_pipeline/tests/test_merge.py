"""
Unit tests for the incremental merge module.

Tests cover:
- Loading base dataset (existing file, missing file, malformed file)
- Confidence-based field merge (higher/equal/lower confidence)
- Field status auditability recording
- Record preservation (base records not in incoming are kept)
- Image merge without force flag (append to image_urls, keep existing primary)
- Image merge with force flag (replace image_url)
- Atomic write (save_dataset)
- Full incremental_merge cycle
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from kr_unified_pipeline.merge import (
    _confidence_rank,
    _is_empty,
    _merge_single_record,
    incremental_merge,
    load_base_dataset,
    merge_records,
    save_dataset,
)
from kr_unified_pipeline.models import CityRecord, ImageSource


@pytest.fixture
def work_dir():
    """Create a temporary directory inside the project for file I/O tests."""
    base = Path(__file__).resolve().parent / "_test_tmp"
    base.mkdir(exist_ok=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_record(
    city_id: str = "KR-11-SEOUL",
    city_name_ko: str = "서울시",
    prefecture_id: str = "KR-11",
    latitude: float | None = 37.5,
    longitude: float | None = 127.0,
    description: str = "수도",
    data_confidence: str = "high",
    source_name: str = "wikipedia",
    image_url: str | None = None,
    image_urls: list[ImageSource] | None = None,
    **kwargs,
) -> CityRecord:
    return CityRecord(
        city_id=city_id,
        city_name_ko=city_name_ko,
        prefecture_id=prefecture_id,
        latitude=latitude,
        longitude=longitude,
        description=description,
        data_confidence=data_confidence,
        source_name=source_name,
        image_url=image_url,
        image_urls=image_urls or [],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests: _confidence_rank
# ---------------------------------------------------------------------------


class TestConfidenceRank:
    def test_known_levels(self):
        assert _confidence_rank("low") == 0
        assert _confidence_rank("medium") == 1
        assert _confidence_rank("high") == 2

    def test_unknown_level_defaults_to_zero(self):
        assert _confidence_rank("unknown") == 0
        assert _confidence_rank("") == 0


# ---------------------------------------------------------------------------
# Tests: _is_empty
# ---------------------------------------------------------------------------


class TestIsEmpty:
    def test_none_is_empty(self):
        assert _is_empty(None) is True

    def test_empty_string_is_empty(self):
        assert _is_empty("") is True

    def test_whitespace_is_empty(self):
        assert _is_empty("   ") is True

    def test_non_empty_string(self):
        assert _is_empty("hello") is False

    def test_zero_is_not_empty(self):
        assert _is_empty(0) is False

    def test_float_is_not_empty(self):
        assert _is_empty(37.5) is False


# ---------------------------------------------------------------------------
# Tests: load_base_dataset
# ---------------------------------------------------------------------------


class TestLoadBaseDataset:
    def test_missing_file_returns_empty(self, work_dir):
        path = work_dir / "cities.json"
        result = load_base_dataset(path)
        assert result == {}

    def test_valid_file_loads_records(self, work_dir):
        records = [
            {"city_id": "KR-11-SEOUL", "city_name_ko": "서울시", "prefecture_id": "KR-11", "data_confidence": "high"},
            {"city_id": "KR-26-BUSAN", "city_name_ko": "부산시", "prefecture_id": "KR-26", "data_confidence": "medium"},
        ]
        path = work_dir / "cities.json"
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

        result = load_base_dataset(path)
        assert len(result) == 2
        assert "KR-11-SEOUL" in result
        assert "KR-26-BUSAN" in result
        assert result["KR-11-SEOUL"].city_name_ko == "서울시"

    def test_malformed_json_returns_empty(self, work_dir):
        path = work_dir / "malformed.json"
        path.write_text("not valid json{{{", encoding="utf-8")
        result = load_base_dataset(path)
        assert result == {}

    def test_non_array_json_returns_empty(self, work_dir):
        path = work_dir / "object.json"
        path.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        result = load_base_dataset(path)
        assert result == {}

    def test_skips_records_without_city_id(self, work_dir):
        records = [
            {"city_name_ko": "이름만"},
            {"city_id": "KR-11-SEOUL", "city_name_ko": "서울시"},
        ]
        path = work_dir / "partial.json"
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        result = load_base_dataset(path)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests: merge_records - confidence precedence
# ---------------------------------------------------------------------------


class TestMergeConfidence:
    def test_higher_confidence_overwrites(self):
        base = {
            "KR-11-SEOUL": _make_record(
                data_confidence="medium",
                description="기존 설명",
            )
        }
        incoming = [
            _make_record(
                data_confidence="high",
                description="새 설명",
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming)
        assert result["KR-11-SEOUL"].description == "새 설명"
        assert result["KR-11-SEOUL"].data_confidence == "high"

    def test_equal_confidence_overwrites(self):
        base = {
            "KR-11-SEOUL": _make_record(
                data_confidence="medium",
                description="기존",
            )
        }
        incoming = [
            _make_record(
                data_confidence="medium",
                description="새것",
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming)
        assert result["KR-11-SEOUL"].description == "새것"

    def test_lower_confidence_does_not_overwrite(self):
        base = {
            "KR-11-SEOUL": _make_record(
                data_confidence="high",
                description="기존 고품질",
            )
        }
        incoming = [
            _make_record(
                data_confidence="low",
                description="저품질",
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming)
        # Fields should NOT be overwritten
        assert result["KR-11-SEOUL"].description == "기존 고품질"
        # Confidence should NOT be downgraded
        assert result["KR-11-SEOUL"].data_confidence == "high"

    def test_never_overwrite_valid_with_empty(self):
        base = {
            "KR-11-SEOUL": _make_record(
                data_confidence="medium",
                description="유효한 설명",
            )
        }
        incoming = [
            _make_record(
                data_confidence="high",
                description="",  # Empty incoming
            )
        ]
        result = merge_records(base, incoming)
        # Valid data preserved even with higher confidence incoming
        assert result["KR-11-SEOUL"].description == "유효한 설명"


# ---------------------------------------------------------------------------
# Tests: field_status auditability (Requirement 9.3)
# ---------------------------------------------------------------------------


class TestFieldStatusAudit:
    def test_records_source_on_update(self):
        base = {
            "KR-11-SEOUL": _make_record(
                data_confidence="medium",
                description="기존",
                source_name="wikipedia",
            )
        }
        incoming = [
            _make_record(
                data_confidence="high",
                description="새것",
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming)
        fs = result["KR-11-SEOUL"].field_status
        assert "description" in fs
        assert "prev_source=wikipedia" in fs["description"]
        assert "new_source=tourapi" in fs["description"]

    def test_records_update_source_when_filling_empty(self):
        base = {
            "KR-11-SEOUL": _make_record(
                data_confidence="medium",
                description="",
                source_name="old_source",
            )
        }
        incoming = [
            _make_record(
                data_confidence="medium",
                description="새 설명",
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming)
        fs = result["KR-11-SEOUL"].field_status
        assert "description" in fs
        assert "source=tourapi" in fs["description"]


# ---------------------------------------------------------------------------
# Tests: preserve all base records (Requirement 9.4)
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_base_records_preserved_when_not_in_incoming(self):
        base = {
            "KR-11-SEOUL": _make_record(city_id="KR-11-SEOUL"),
            "KR-26-BUSAN": _make_record(city_id="KR-26-BUSAN", city_name_ko="부산시"),
        }
        incoming = [
            _make_record(city_id="KR-11-SEOUL", description="업데이트"),
        ]
        result = merge_records(base, incoming)
        assert "KR-11-SEOUL" in result
        assert "KR-26-BUSAN" in result
        assert result["KR-26-BUSAN"].city_name_ko == "부산시"

    def test_new_records_added(self):
        base = {
            "KR-11-SEOUL": _make_record(city_id="KR-11-SEOUL"),
        }
        incoming = [
            _make_record(city_id="KR-42-GANGWON", city_name_ko="강원도"),
        ]
        result = merge_records(base, incoming)
        assert "KR-11-SEOUL" in result
        assert "KR-42-GANGWON" in result

    def test_empty_incoming_preserves_all_base(self):
        base = {
            "KR-11-SEOUL": _make_record(city_id="KR-11-SEOUL"),
            "KR-26-BUSAN": _make_record(city_id="KR-26-BUSAN"),
        }
        result = merge_records(base, [])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests: image merge (Requirement 9.5)
# ---------------------------------------------------------------------------


class TestImageMerge:
    def test_without_force_keeps_existing_primary(self):
        base = {
            "KR-11-SEOUL": _make_record(
                image_url="https://wiki.example.com/seoul.jpg",
                image_urls=[ImageSource(url="https://wiki.example.com/seoul.jpg", source="wikipedia")],
            )
        }
        incoming = [
            _make_record(
                image_url="https://tourapi.example.com/new.jpg",
                image_urls=[ImageSource(url="https://tourapi.example.com/new.jpg", source="tourapi")],
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming, force_image_update=False)
        record = result["KR-11-SEOUL"]
        # Existing primary preserved
        assert record.image_url == "https://wiki.example.com/seoul.jpg"
        # New URL appended to image_urls
        urls = [img.url for img in record.image_urls]
        assert "https://tourapi.example.com/new.jpg" in urls

    def test_with_force_replaces_primary(self):
        base = {
            "KR-11-SEOUL": _make_record(
                image_url="https://wiki.example.com/old.jpg",
                image_urls=[ImageSource(url="https://wiki.example.com/old.jpg", source="wikipedia")],
            )
        }
        incoming = [
            _make_record(
                image_url="https://tourapi.example.com/new.jpg",
                image_urls=[ImageSource(url="https://tourapi.example.com/new.jpg", source="tourapi")],
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming, force_image_update=True)
        record = result["KR-11-SEOUL"]
        # Primary replaced
        assert record.image_url == "https://tourapi.example.com/new.jpg"

    def test_no_existing_image_accepts_new(self):
        base = {
            "KR-11-SEOUL": _make_record(image_url=None, image_urls=[])
        }
        incoming = [
            _make_record(
                image_url="https://wiki.example.com/seoul.jpg",
                image_urls=[ImageSource(url="https://wiki.example.com/seoul.jpg", source="wikipedia")],
            )
        ]
        result = merge_records(base, incoming, force_image_update=False)
        record = result["KR-11-SEOUL"]
        assert record.image_url == "https://wiki.example.com/seoul.jpg"

    def test_no_duplicate_image_urls(self):
        base = {
            "KR-11-SEOUL": _make_record(
                image_url="https://wiki.example.com/seoul.jpg",
                image_urls=[ImageSource(url="https://wiki.example.com/seoul.jpg", source="wikipedia")],
            )
        }
        incoming = [
            _make_record(
                image_url="https://wiki.example.com/seoul.jpg",  # Same URL
                image_urls=[ImageSource(url="https://wiki.example.com/seoul.jpg", source="wikipedia")],
            )
        ]
        result = merge_records(base, incoming, force_image_update=False)
        record = result["KR-11-SEOUL"]
        # No duplicates in image_urls
        assert len(record.image_urls) == 1

    def test_image_merge_works_even_with_lower_confidence(self):
        """Image merging is additive regardless of confidence level."""
        base = {
            "KR-11-SEOUL": _make_record(
                data_confidence="high",
                image_url="https://wiki.example.com/old.jpg",
                image_urls=[ImageSource(url="https://wiki.example.com/old.jpg", source="wikipedia")],
            )
        }
        incoming = [
            _make_record(
                data_confidence="low",
                image_url="https://tourapi.example.com/new.jpg",
                image_urls=[ImageSource(url="https://tourapi.example.com/new.jpg", source="tourapi")],
                source_name="tourapi",
            )
        ]
        result = merge_records(base, incoming, force_image_update=False)
        record = result["KR-11-SEOUL"]
        # Image_urls should have both even though confidence is lower
        urls = [img.url for img in record.image_urls]
        assert "https://tourapi.example.com/new.jpg" in urls


# ---------------------------------------------------------------------------
# Tests: save_dataset (atomic write)
# ---------------------------------------------------------------------------


class TestSaveDataset:
    def test_writes_valid_json(self, work_dir):
        dataset = {
            "KR-11-SEOUL": _make_record(city_id="KR-11-SEOUL"),
        }
        path = work_dir / "save_test.json"
        save_dataset(dataset, path)

        content = json.loads(path.read_text(encoding="utf-8"))
        assert len(content) == 1
        assert content[0]["city_id"] == "KR-11-SEOUL"

    def test_creates_parent_directories(self, work_dir):
        path = work_dir / "deep" / "nested" / "cities.json"
        dataset = {"KR-11-SEOUL": _make_record()}
        save_dataset(dataset, path)
        assert path.exists()

    def test_overwrites_existing_file(self, work_dir):
        path = work_dir / "overwrite.json"
        path.write_text("old content", encoding="utf-8")
        dataset = {"KR-11-SEOUL": _make_record()}
        save_dataset(dataset, path)
        content = json.loads(path.read_text(encoding="utf-8"))
        assert content[0]["city_id"] == "KR-11-SEOUL"


# ---------------------------------------------------------------------------
# Tests: incremental_merge (full cycle)
# ---------------------------------------------------------------------------


class TestIncrementalMerge:
    def test_full_cycle_with_existing_file(self, work_dir):
        path = work_dir / "cycle_existing.json"
        # Write initial data
        initial = [
            {"city_id": "KR-11-SEOUL", "city_name_ko": "서울시", "data_confidence": "medium", "description": "기존"},
        ]
        path.write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")

        # Merge new data
        incoming = [
            _make_record(
                city_id="KR-11-SEOUL",
                data_confidence="high",
                description="업데이트됨",
                source_name="tourapi",
            ),
            _make_record(
                city_id="KR-42-GANGWON",
                city_name_ko="강원도",
                data_confidence="medium",
            ),
        ]
        result = incremental_merge(path, incoming)

        # Verify in-memory result
        assert len(result) == 2
        assert result["KR-11-SEOUL"].description == "업데이트됨"
        assert "KR-42-GANGWON" in result

        # Verify file was written
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert len(saved) == 2

    def test_full_cycle_missing_file(self, work_dir):
        path = work_dir / "cycle_missing.json"
        incoming = [
            _make_record(city_id="KR-11-SEOUL"),
        ]
        result = incremental_merge(path, incoming)
        assert len(result) == 1
        assert path.exists()

    def test_full_cycle_empty_incoming(self, work_dir):
        path = work_dir / "cycle_empty.json"
        initial = [{"city_id": "KR-11-SEOUL", "city_name_ko": "서울시"}]
        path.write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")

        result = incremental_merge(path, [])
        assert len(result) == 1
        assert result["KR-11-SEOUL"].city_name_ko == "서울시"
