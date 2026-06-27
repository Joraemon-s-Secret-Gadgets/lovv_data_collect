"""
Unit tests for ReviewTransition.

Validates Requirements 4.1, 4.2, 4.3, 4.4, 4.5.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kr_unified_pipeline.completeness import (
    STATUS_COLLECTED,
    STATUS_NEEDS_REVIEW,
    CompletenessEvaluator,
)
from kr_unified_pipeline.models import CityRecord, CompletenessResult, ReviewEntry
from kr_unified_pipeline.review_transition import ReviewTransition


@pytest.fixture
def transition() -> ReviewTransition:
    return ReviewTransition()


@pytest.fixture
def evaluator() -> CompletenessEvaluator:
    return CompletenessEvaluator()


@pytest.fixture
def complete_record() -> CityRecord:
    """A fully complete CityRecord with all required fields and image."""
    return CityRecord(
        city_id="KR-11-001",
        city_name_ko="서울특별시",
        prefecture_id="KR-11",
        latitude=37.5665,
        longitude=126.9780,
        description="대한민국의 수도이자 최대 도시",
        image_url="https://upload.wikimedia.org/seoul.jpg",
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
        image_url=None,
    )


class TestTransitionFieldStatus:
    """Requirement 4.1: Update record field_status with specific fields requiring attention."""

    def test_transition_updates_field_status_from_result(
        self, transition: ReviewTransition, incomplete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(incomplete_record)
        transition.transition(incomplete_record, result)

        assert incomplete_record.field_status["latitude"] == STATUS_NEEDS_REVIEW
        assert incomplete_record.field_status["longitude"] == STATUS_NEEDS_REVIEW
        assert incomplete_record.field_status["description"] == STATUS_NEEDS_REVIEW

    def test_transition_marks_collected_fields(
        self, transition: ReviewTransition, incomplete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(incomplete_record)
        transition.transition(incomplete_record, result)

        assert incomplete_record.field_status["city_name_ko"] == STATUS_COLLECTED
        assert incomplete_record.field_status["prefecture_id"] == STATUS_COLLECTED

    def test_transition_marks_missing_image_url(
        self, transition: ReviewTransition, incomplete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(incomplete_record)
        transition.transition(incomplete_record, result)

        assert incomplete_record.field_status["image_url"] == STATUS_NEEDS_REVIEW

    def test_transition_does_not_mark_image_when_present(
        self, transition: ReviewTransition, complete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(complete_record)
        transition.transition(complete_record, result)

        # image_url should not be marked as needs_review since it's present
        assert complete_record.field_status.get("image_url") != STATUS_NEEDS_REVIEW

    def test_transition_updates_data_confidence(
        self, transition: ReviewTransition, incomplete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(incomplete_record)
        transition.transition(incomplete_record, result)

        assert incomplete_record.data_confidence == "medium"


class TestReviewReason:
    """Requirement 4.2: Generate review_reason field."""

    def test_missing_coordinates_reason(self, transition: ReviewTransition, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_id="KR-42-001",
            city_name_ko="춘천시",
            prefecture_id="KR-42",
            latitude=None,
            longitude=None,
            description="강원도의 도청소재지",
            image_url="https://example.com/img.jpg",
        )
        result = evaluator.evaluate(record)
        entry = transition.build_review_entry(record, result)
        assert entry.review_reason == "missing_coordinates"

    def test_empty_description_reason(self, transition: ReviewTransition, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_id="KR-11-002",
            city_name_ko="강남구",
            prefecture_id="KR-11",
            latitude=37.4979,
            longitude=127.0276,
            description="",
            image_url="https://example.com/img.jpg",
        )
        result = evaluator.evaluate(record)
        entry = transition.build_review_entry(record, result)
        assert entry.review_reason == "empty_description"

    def test_no_image_url_reason(self, transition: ReviewTransition, evaluator: CompletenessEvaluator) -> None:
        record = CityRecord(
            city_id="KR-11-001",
            city_name_ko="서울특별시",
            prefecture_id="KR-11",
            latitude=37.5665,
            longitude=126.9780,
            description="대한민국의 수도",
            image_url=None,
        )
        result = evaluator.evaluate(record)
        entry = transition.build_review_entry(record, result)
        assert entry.review_reason == "no_image_url"

    def test_priority_coordinates_over_description(self, transition: ReviewTransition, evaluator: CompletenessEvaluator) -> None:
        """When both coordinates and description are missing, coordinates takes priority."""
        record = CityRecord(
            city_id="KR-42-001",
            city_name_ko="춘천시",
            prefecture_id="KR-42",
            latitude=None,
            longitude=None,
            description="",
            image_url="https://example.com/img.jpg",
        )
        result = evaluator.evaluate(record)
        entry = transition.build_review_entry(record, result)
        assert entry.review_reason == "missing_coordinates"


class TestUpgradeIfComplete:
    """Requirement 4.4: Restore STATUS_COLLECTED when data is now complete."""

    def test_upgrade_restores_collected_status(
        self, transition: ReviewTransition, evaluator: CompletenessEvaluator
    ) -> None:
        # Start with incomplete record that was previously flagged
        record = CityRecord(
            city_id="KR-42-001",
            city_name_ko="춘천시",
            prefecture_id="KR-42",
            latitude=None,
            longitude=None,
            description="",
            field_status={
                "latitude": STATUS_NEEDS_REVIEW,
                "longitude": STATUS_NEEDS_REVIEW,
                "description": STATUS_NEEDS_REVIEW,
            },
            data_confidence="medium",
        )

        # Now simulate the record being completed in a subsequent run
        record.latitude = 37.8813
        record.longitude = 127.7298
        record.description = "강원도의 도청소재지"
        record.image_url = "https://example.com/img.jpg"

        result = evaluator.evaluate(record)
        transition.upgrade_if_complete(record, result)

        assert record.field_status["latitude"] == STATUS_COLLECTED
        assert record.field_status["longitude"] == STATUS_COLLECTED
        assert record.field_status["description"] == STATUS_COLLECTED
        assert record.field_status["city_name_ko"] == STATUS_COLLECTED
        assert record.field_status["prefecture_id"] == STATUS_COLLECTED
        assert record.field_status["image_url"] == STATUS_COLLECTED
        assert record.data_confidence == "high"

    def test_no_upgrade_when_still_incomplete(
        self, transition: ReviewTransition, evaluator: CompletenessEvaluator
    ) -> None:
        record = CityRecord(
            city_id="KR-42-001",
            city_name_ko="춘천시",
            prefecture_id="KR-42",
            latitude=None,
            longitude=None,
            description="",
            field_status={
                "latitude": STATUS_NEEDS_REVIEW,
                "longitude": STATUS_NEEDS_REVIEW,
                "description": STATUS_NEEDS_REVIEW,
            },
        )

        result = evaluator.evaluate(record)
        transition.upgrade_if_complete(record, result)

        # Should NOT upgrade since data is still missing
        assert record.field_status["latitude"] == STATUS_NEEDS_REVIEW
        assert record.field_status["longitude"] == STATUS_NEEDS_REVIEW
        assert record.field_status["description"] == STATUS_NEEDS_REVIEW

    def test_upgrade_with_image_present(
        self, transition: ReviewTransition, evaluator: CompletenessEvaluator
    ) -> None:
        record = CityRecord(
            city_id="KR-11-001",
            city_name_ko="서울특별시",
            prefecture_id="KR-11",
            latitude=37.5665,
            longitude=126.9780,
            description="대한민국의 수도",
            image_url="https://example.com/seoul.jpg",
            field_status={"image_url": STATUS_NEEDS_REVIEW},
        )

        result = evaluator.evaluate(record)
        transition.upgrade_if_complete(record, result)

        assert record.field_status["image_url"] == STATUS_COLLECTED


class TestBuildReviewEntry:
    """Requirement 4.3, 4.5: Review manifest entry creation."""

    def test_entry_contains_all_required_fields(
        self, transition: ReviewTransition, incomplete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(incomplete_record)
        entry = transition.build_review_entry(incomplete_record, result)

        assert entry.city_id == "KR-42-001"
        assert entry.city_name_ko == "춘천시"
        assert entry.prefecture_id == "KR-42"
        assert len(entry.missing_fields) > 0
        assert entry.review_reason != ""
        assert entry.flagged_at != ""

    def test_entry_has_iso8601_timestamp(
        self, transition: ReviewTransition, incomplete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(incomplete_record)
        entry = transition.build_review_entry(incomplete_record, result)

        # Verify it's a valid ISO 8601 timestamp
        parsed = datetime.fromisoformat(entry.flagged_at)
        assert parsed.tzinfo is not None  # Must be timezone-aware

    def test_entry_includes_missing_fields(
        self, transition: ReviewTransition, incomplete_record: CityRecord, evaluator: CompletenessEvaluator
    ) -> None:
        result = evaluator.evaluate(incomplete_record)
        entry = transition.build_review_entry(incomplete_record, result)

        assert "latitude" in entry.missing_fields
        assert "longitude" in entry.missing_fields
        assert "description" in entry.missing_fields
        assert "image_url" in entry.missing_fields

    def test_entry_for_record_missing_only_image(
        self, transition: ReviewTransition, evaluator: CompletenessEvaluator
    ) -> None:
        record = CityRecord(
            city_id="KR-11-001",
            city_name_ko="서울특별시",
            prefecture_id="KR-11",
            latitude=37.5665,
            longitude=126.9780,
            description="대한민국의 수도",
            image_url=None,
        )
        result = evaluator.evaluate(record)
        entry = transition.build_review_entry(record, result)

        assert entry.review_reason == "no_image_url"
        assert "image_url" in entry.missing_fields
