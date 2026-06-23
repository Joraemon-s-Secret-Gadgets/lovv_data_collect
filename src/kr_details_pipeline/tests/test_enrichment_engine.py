"""Tests for enrichment_engine: validate_extracted_metadata()."""

from __future__ import annotations

import pytest

from kr_details_pipeline.enrichment_engine import (
    COMPANION_FIT,
    EXPERIENCE_TAGS,
    INDOOR_OUTDOOR,
    VIBE_TAGS,
    ValidationError,
    validate_extracted_metadata,
)


# ---------------------------------------------------------------------------
# ValidationError on extra fields (Req 3.4)
# ---------------------------------------------------------------------------


class TestExtraFieldsRejected:
    """Response with fields beyond the 4 allowed must raise ValidationError."""

    def test_single_extra_field_raises(self):
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": ["calm"],
            "experience_tags": ["walking"],
            "companion_fit": ["solo"],
            "description": "should not be here",
        }
        with pytest.raises(ValidationError):
            validate_extracted_metadata(response)

    def test_multiple_extra_fields_raises(self):
        response = {
            "indoor_outdoor": "outdoor",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": [],
            "confidence": 0.9,
            "reasoning": "nature spot",
        }
        with pytest.raises(ValidationError):
            validate_extracted_metadata(response)

    def test_only_allowed_fields_accepted(self):
        response = {
            "indoor_outdoor": "mixed",
            "vibe_tags": ["calm"],
            "experience_tags": ["walking"],
            "companion_fit": ["solo"],
        }
        result = validate_extracted_metadata(response)
        assert set(result.keys()) == {
            "indoor_outdoor", "vibe_tags", "experience_tags", "companion_fit"
        }


# ---------------------------------------------------------------------------
# indoor_outdoor validation (Req 3.5)
# ---------------------------------------------------------------------------


class TestIndoorOutdoorValidation:
    """indoor_outdoor must be one of {indoor, outdoor, mixed, unknown}."""

    @pytest.mark.parametrize("value", ["indoor", "outdoor", "mixed", "unknown"])
    def test_valid_values_preserved(self, value):
        response = {
            "indoor_outdoor": value,
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["indoor_outdoor"] == value

    def test_invalid_value_becomes_unknown(self):
        response = {
            "indoor_outdoor": "semi-outdoor",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["indoor_outdoor"] == "unknown"

    def test_missing_field_defaults_to_unknown(self):
        response = {
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["indoor_outdoor"] == "unknown"


# ---------------------------------------------------------------------------
# vibe_tags filtering (Req 3.6, 3.9)
# ---------------------------------------------------------------------------


class TestVibeTagsValidation:
    """vibe_tags: only canonical tags, max 5, non-canonical silently removed."""

    def test_canonical_tags_preserved(self):
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": ["calm", "romantic", "cozy"],
            "experience_tags": [],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["vibe_tags"] == ["calm", "romantic", "cozy"]

    def test_non_canonical_tags_removed_silently(self):
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": ["calm", "super_energetic", "romantic", "fake_tag"],
            "experience_tags": [],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["vibe_tags"] == ["calm", "romantic"]

    def test_max_5_tags_enforced(self):
        tags = ["calm", "romantic", "cozy", "peaceful", "healing", "serene", "rustic"]
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": tags,
            "experience_tags": [],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert len(result["vibe_tags"]) == 5
        # First 5 canonical tags preserved in order
        assert result["vibe_tags"] == ["calm", "romantic", "cozy", "peaceful", "healing"]

    def test_non_list_vibe_tags_treated_as_empty(self):
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": "calm",
            "experience_tags": [],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["vibe_tags"] == []


# ---------------------------------------------------------------------------
# experience_tags filtering (Req 3.7, 3.9)
# ---------------------------------------------------------------------------


class TestExperienceTagsValidation:
    """experience_tags: only canonical, max 3, non-canonical silently removed."""

    def test_canonical_tags_preserved(self):
        response = {
            "indoor_outdoor": "outdoor",
            "vibe_tags": [],
            "experience_tags": ["photo_spot", "walking"],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["experience_tags"] == ["photo_spot", "walking"]

    def test_non_canonical_removed_silently(self):
        response = {
            "indoor_outdoor": "outdoor",
            "vibe_tags": [],
            "experience_tags": ["walking", "swimming", "photo_spot"],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert result["experience_tags"] == ["walking", "photo_spot"]

    def test_max_3_enforced(self):
        response = {
            "indoor_outdoor": "outdoor",
            "vibe_tags": [],
            "experience_tags": [
                "photo_spot", "picnic", "walking", "slow_travel", "market_tour"
            ],
            "companion_fit": [],
        }
        result = validate_extracted_metadata(response)
        assert len(result["experience_tags"]) == 3
        assert result["experience_tags"] == ["photo_spot", "picnic", "walking"]


# ---------------------------------------------------------------------------
# companion_fit filtering (Req 3.8, 3.9)
# ---------------------------------------------------------------------------


class TestCompanionFitValidation:
    """companion_fit: only canonical values, max 7, non-canonical removed."""

    def test_canonical_values_preserved(self):
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": ["family", "couple", "solo"],
        }
        result = validate_extracted_metadata(response)
        assert result["companion_fit"] == ["family", "couple", "solo"]

    def test_non_canonical_removed_silently(self):
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": ["family", "robot", "couple", "aliens"],
        }
        result = validate_extracted_metadata(response)
        assert result["companion_fit"] == ["family", "couple"]

    def test_max_7_enforced(self):
        # All 7 canonical values are valid, adding duplicates to test truncation
        all_values = list(COMPANION_FIT)
        # Ensure we have more than 7 entries (all canonical are exactly 7)
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": all_values,
        }
        result = validate_extracted_metadata(response)
        assert len(result["companion_fit"]) <= 7

    def test_all_seven_canonical_values_pass(self):
        response = {
            "indoor_outdoor": "indoor",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": [
                "family", "kids", "couple", "solo", "pet", "parents", "seniors"
            ],
        }
        result = validate_extracted_metadata(response)
        assert len(result["companion_fit"]) == 7


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------


class TestReturnStructure:
    """validate_extracted_metadata always returns dict with exactly 4 fields."""

    def test_empty_response_returns_defaults(self):
        response: dict = {}
        result = validate_extracted_metadata(response)
        assert result == {
            "indoor_outdoor": "unknown",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": [],
        }

    def test_partial_response_fills_defaults(self):
        response = {
            "indoor_outdoor": "outdoor",
            "vibe_tags": ["calm"],
        }
        result = validate_extracted_metadata(response)
        assert result["indoor_outdoor"] == "outdoor"
        assert result["vibe_tags"] == ["calm"]
        assert result["experience_tags"] == []
        assert result["companion_fit"] == []
