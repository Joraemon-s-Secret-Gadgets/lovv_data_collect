import json
from decimal import Decimal

import pytest

from kr_vector_index.metadata import (
    FILTERABLE_METADATA_KEYS,
    FORBIDDEN_METADATA_KEYS,
    MetadataValidationError,
    build_enriched_metadata,
    trim_to_budget,
    validate_metadata,
)


def test_validate_metadata_accepts_allowlisted_keys() -> None:
    metadata = {
        "country": "KR",
        "entity_type": "attraction",
        "city_id": "KR-Andong",
        "theme_tags": ["한식"],
        "raw_s3_uri": "s3://bucket/key.json",
        "ddb_pk": "CITY#Andong",
        "ddb_sk": "ATTRACTION#100",
        "embedding_model": "amazon.titan-embed-text-v2:0",
    }

    assert validate_metadata(metadata) == metadata


def test_validate_metadata_rejects_unknown_key() -> None:
    with pytest.raises(MetadataValidationError, match="not allowlisted"):
        validate_metadata({"country": "KR", "unknown": "value"})


def test_validate_metadata_rejects_large_filterable_metadata() -> None:
    with pytest.raises(MetadataValidationError, match="filterable metadata"):
        validate_metadata({"country": "KR", "title": "x" * 3000})


def test_validate_metadata_normalizes_decimal_values() -> None:
    metadata = validate_metadata({"latitude": Decimal("36.5"), "longitude": Decimal("128.1")})

    assert metadata == {"latitude": 36.5, "longitude": 128.1}

class TestTrimToBudget:
    def test_returns_metadata_as_is_when_under_budget(self) -> None:
        metadata = {"entity_type": "attraction", "title": "Test Place"}
        result = trim_to_budget(metadata)
        assert result == metadata
        assert result is not metadata

    def test_trims_experience_tags_first(self) -> None:
        metadata = {
            "entity_type": "attraction",
            "title": "x" * 1900,
            "experience_tags": ["photo_spot", "picnic", "walking"],
            "vibe_tags": ["romantic", "nostalgic", "cozy", "meditative", "refreshing"],
        }
        result = trim_to_budget(metadata)
        assert result is not None
        assert len(result["experience_tags"]) < 3 or len(result["vibe_tags"]) < 5

    def test_trims_vibe_tags_after_experience_tags_exhausted(self) -> None:
        metadata = {
            "entity_type": "attraction",
            "title": "x" * 1950,
            "experience_tags": ["photo_spot"],
            "vibe_tags": ["romantic", "nostalgic", "cozy", "meditative", "refreshing"],
        }
        result = trim_to_budget(metadata)
        assert result is not None
        filterable = {k: v for k, v in result.items() if k in FILTERABLE_METADATA_KEYS}
        size = len(json.dumps(filterable, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        assert size <= 2048

    def test_returns_none_when_cannot_fit(self) -> None:
        metadata = {
            "entity_type": "attraction",
            "title": "x" * 2100,
        }
        result = trim_to_budget(metadata)
        assert result is None

    def test_does_not_mutate_input(self) -> None:
        metadata = {
            "entity_type": "attraction",
            "title": "x" * 1950,
            "experience_tags": ["photo_spot", "picnic", "walking"],
            "vibe_tags": ["romantic", "nostalgic"],
        }
        original_exp_tags = metadata["experience_tags"].copy()
        trim_to_budget(metadata)
        assert metadata["experience_tags"] == original_exp_tags

    def test_custom_budget(self) -> None:
        metadata = {"entity_type": "attraction", "title": "hello"}
        result = trim_to_budget(metadata, budget=10)
        assert result is None

    def test_only_checks_filterable_keys(self) -> None:
        large_non_filterable_uri = "s3://bucket/" + "x" * 3000
        metadata = {
            "entity_type": "attraction",
            "title": "short",
            "raw_s3_uri": large_non_filterable_uri,
        }
        result = trim_to_budget(metadata)
        assert result is not None


def test_build_enriched_metadata_includes_enrichment_fields_when_succeeded() -> None:
    item = {
        "entity_type": "attraction",
        "title": "산악 공원",
        "indoor_outdoor": "outdoor",
        "vibe_tags": ["refreshing", "mountain_view"],
        "experience_tags": ["walking"],
        "companion_fit": ["family", "couple"],
        "schema_version": "2",
        "attraction_subtype_code": "NA010100",
        "metadata_enrichment": {"status": "succeeded"},
    }

    result = build_enriched_metadata(item)

    assert result["indoor_outdoor"] == "outdoor"
    assert result["vibe_tags"] == ["refreshing", "mountain_view"]
    assert result["experience_tags"] == ["walking"]
    assert result["companion_fit"] == ["family", "couple"]
    assert result["schema_version"] == "2"
    assert result["attraction_subtype_code"] == "NA010100"


def test_build_enriched_metadata_excludes_enrichment_fields_when_not_succeeded() -> None:
    item = {
        "entity_type": "attraction",
        "title": "산악 공원",
        "indoor_outdoor": "outdoor",
        "vibe_tags": ["refreshing"],
        "experience_tags": ["walking"],
        "companion_fit": ["family"],
        "schema_version": "2",
        "attraction_subtype_code": "NA010100",
        "metadata_enrichment": {"status": "failed"},
    }

    result = build_enriched_metadata(item)

    assert "indoor_outdoor" not in result
    assert "vibe_tags" not in result
    assert "experience_tags" not in result
    assert "companion_fit" not in result
    assert "schema_version" not in result
    assert result["attraction_subtype_code"] == "NA010100"
    assert result["entity_type"] == "attraction"


def test_build_enriched_metadata_excludes_enrichment_fields_when_no_metadata_enrichment() -> None:
    item = {
        "entity_type": "attraction",
        "title": "산악 공원",
        "indoor_outdoor": "outdoor",
        "vibe_tags": ["refreshing"],
    }

    result = build_enriched_metadata(item)

    assert "indoor_outdoor" not in result
    assert "vibe_tags" not in result


def test_build_enriched_metadata_strips_none_empty_string_empty_array() -> None:
    item = {
        "entity_type": "attraction",
        "title": None,
        "city_name_en": "",
        "theme_tags": [],
        "province": "경상북도",
        "metadata_enrichment": {"status": "succeeded"},
        "vibe_tags": [],
        "indoor_outdoor": "",
    }

    result = build_enriched_metadata(item)

    assert "title" not in result
    assert "city_name_en" not in result
    assert "theme_tags" not in result
    assert "vibe_tags" not in result
    assert "indoor_outdoor" not in result
    assert result["province"] == "경상북도"


def test_build_enriched_metadata_excludes_forbidden_fields() -> None:
    item = {
        "entity_type": "attraction",
        "title": "테스트",
        "description": "긴 설명 텍스트",
        "overview": "개요 텍스트",
        "opening_hours": "09:00~18:00",
        "closed_days": "매주 월요일",
        "experience_guide": "가이드 텍스트",
        "parking": "무료",
        "homepage": "https://example.com",
        "image_url": "https://example.com/img.jpg",
        "metadata_enrichment": {"status": "succeeded"},
    }

    result = build_enriched_metadata(item)

    for key in FORBIDDEN_METADATA_KEYS:
        assert key not in result
    assert result["entity_type"] == "attraction"
    assert result["title"] == "테스트"


def test_build_enriched_metadata_normalizes_decimals() -> None:
    item = {
        "latitude": Decimal("36.5"),
        "longitude": Decimal("128"),
        "metadata_enrichment": {"status": "succeeded"},
    }

    result = build_enriched_metadata(item)

    assert result["latitude"] == 36.5
    assert result["longitude"] == 128
