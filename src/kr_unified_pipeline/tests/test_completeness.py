"""
Unit tests for CompletenessEvaluator.

Validates Requirements 3.1, 3.2, 3.3, 3.4, 3.5.
"""

from __future__ import annotations

import pytest

from kr_unified_pipeline.completeness import (
    STATUS_COLLECTED,
    STATUS_MISSING,
    STATUS_NEEDS_REVIEW,
    CompletenessEvaluator,
)
from kr_unified_pipeline.models import CityRecord


@pytest.fixture
def evaluator() -> CompletenessEvaluator:
    return CompletenessEvaluator()


@pytest.fixture
def complete_record() -> CityRecord:
    """A fully complete CityRecord with all required fields present."""
    return CityRecord(
        city_id="KR-11-001",
        city_name_ko="서울특별시",
        prefecture_id="KR-11",
        latitude=37.5665,
        longitude=126.9780,
        description="대한민국의 수도이자 최대 도시",
    )


@pytest.fixture
def incomplete_record() -> CityRecord:
    """A CityRecord missing coordinates and description."""
    return CityRecord(
        city_id="KR-42-001",
        city_name_ko="춘천시",
        prefecture_id="KR-42",
        latitude=None,
        longitude=None,
        description="",
    )


class TestCompletenessEvaluatorRequiredFields:
    """Requirement 3.1: Check presence of required fields."""

    def test_required_fields_constant(self, evaluator: CompletenessEvaluator) -> None:
        assert evaluator.REQUIRED_FIELDS == (
            "city_name_ko",
            "prefecture_id",
            "latitude",
            "longitude",
            "description",
        )

    def test_all_fields_present(self, evaluator: CompletenessEvaluator, complete_record: CityRecord) -> None:
        result = evaluator.evaluate(complete_record)
        assert result.missing_fields == ()
        assert result.data_confidence == "high"
        assert result.needs_review is False

    def test_missing_city_name_ko(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=126.9,
            description="설명",
        )
        result = evaluator.evaluate(record)
        assert "city_name_ko" in result.missing_fields
        assert result.field_statuses["city_name_ko"] == STATUS_MISSING

    def test_missing_prefecture_id(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="",
            latitude=37.5,
            longitude=126.9,
            description="설명",
        )
        result = evaluator.evaluate(record)
        assert "prefecture_id" in result.missing_fields
        assert result.field_statuses["prefecture_id"] == STATUS_MISSING


class TestCompletenessEvaluatorCoordinates:
    """Requirement 3.2: Mark coordinates as STATUS_NEEDS_REVIEW when None."""

    def test_latitude_none(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=None,
            longitude=126.9,
            description="설명",
        )
        result = evaluator.evaluate(record)
        assert "latitude" in result.missing_fields
        assert result.field_statuses["latitude"] == STATUS_NEEDS_REVIEW
        assert "missing_coordinates" in result.review_reasons

    def test_longitude_none(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=None,
            description="설명",
        )
        result = evaluator.evaluate(record)
        assert "longitude" in result.missing_fields
        assert result.field_statuses["longitude"] == STATUS_NEEDS_REVIEW
        assert "missing_coordinates" in result.review_reasons

    def test_both_coordinates_none(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=None,
            longitude=None,
            description="설명",
        )
        result = evaluator.evaluate(record)
        assert "latitude" in result.missing_fields
        assert "longitude" in result.missing_fields
        # Only one "missing_coordinates" reason
        assert result.review_reasons.count("missing_coordinates") == 1


class TestCompletenessEvaluatorDescription:
    """Requirement 3.3: Mark description as STATUS_NEEDS_REVIEW when empty or whitespace-only."""

    def test_empty_description(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=126.9,
            description="",
        )
        result = evaluator.evaluate(record)
        assert "description" in result.missing_fields
        assert result.field_statuses["description"] == STATUS_NEEDS_REVIEW
        assert "empty_description" in result.review_reasons

    def test_whitespace_only_description(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=126.9,
            description="   \t\n  ",
        )
        result = evaluator.evaluate(record)
        assert "description" in result.missing_fields
        assert result.field_statuses["description"] == STATUS_NEEDS_REVIEW
        assert "empty_description" in result.review_reasons

    def test_valid_description(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=126.9,
            description="유효한 설명",
        )
        result = evaluator.evaluate(record)
        assert "description" not in result.missing_fields
        assert result.field_statuses["description"] == STATUS_COLLECTED


class TestCompletenessEvaluatorConfidence:
    """Requirement 3.4: Compute data_confidence score."""

    def test_high_confidence_all_fields_present(self, evaluator: CompletenessEvaluator, complete_record: CityRecord) -> None:
        confidence = evaluator.compute_confidence(complete_record)
        assert confidence == "high"

    def test_medium_confidence_with_name_and_prefecture(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=None,
            longitude=None,
            description="",
        )
        confidence = evaluator.compute_confidence(record)
        assert confidence == "medium"

    def test_low_confidence_missing_city_name(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=126.9,
            description="설명",
        )
        confidence = evaluator.compute_confidence(record)
        assert confidence == "low"

    def test_low_confidence_missing_prefecture(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="",
            latitude=37.5,
            longitude=126.9,
            description="설명",
        )
        confidence = evaluator.compute_confidence(record)
        assert confidence == "low"

    def test_low_confidence_both_missing(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="",
            prefecture_id="",
            latitude=None,
            longitude=None,
            description="",
        )
        confidence = evaluator.compute_confidence(record)
        assert confidence == "low"


class TestCompletenessEvaluatorReviewStatus:
    """Requirement 3.5: Set overall status to STATUS_NEEDS_REVIEW when confidence is low."""

    def test_low_confidence_triggers_needs_review(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="",
            prefecture_id="",
            latitude=None,
            longitude=None,
            description="",
        )
        result = evaluator.evaluate(record)
        assert result.needs_review is True
        assert result.data_confidence == "low"

    def test_medium_confidence_no_review(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=None,
            longitude=None,
            description="",
        )
        result = evaluator.evaluate(record)
        assert result.needs_review is False
        assert result.data_confidence == "medium"

    def test_high_confidence_no_review(self, evaluator: CompletenessEvaluator, complete_record: CityRecord) -> None:
        result = evaluator.evaluate(complete_record)
        assert result.needs_review is False
        assert result.data_confidence == "high"

    def test_whitespace_city_name_treated_as_missing(self, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_name_ko="   ",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=126.9,
            description="설명",
        )
        result = evaluator.evaluate(record)
        assert result.data_confidence == "low"
        assert result.needs_review is True
