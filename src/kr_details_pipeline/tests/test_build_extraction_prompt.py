"""Unit tests for build_extraction_prompt() in enrichment_engine.py."""

from __future__ import annotations

from kr_details_pipeline.enrichment_engine import (
    ALLOWED_PROMPT_FIELDS,
    FORBIDDEN_PROMPT_FIELDS,
    MAX_PROMPT_LENGTH,
    build_extraction_prompt,
)


def _make_attraction_item(**overrides) -> dict:
    """Create a minimal attraction item with optional overrides."""
    base = {
        "entity_type": "attraction",
        "content_id": "12345",
        "title": "예시 관광지",
        "description": "아름다운 관광지 설명입니다.",
        "theme": "자연·트레킹",
        "theme_tags": ["자연·트레킹"],
        "experience_guide": "산책로를 따라 걸으세요.",
        "opening_hours": "09:00~18:00",
        "closed_days": "매주 월요일",
        "parking": "무료주차 가능",
        "address": "경상북도 경주시",
        # Forbidden fields
        "PK": "CITY#gyeongju",
        "SK": "ATTRACTION#12345",
        "source_key": "kr/attractions/12345.json",
        "raw_s3_uri": "s3://lovv-raw-bucket/kr/attractions/12345.json",
        "classification_source": "lcls_systm3",
        "classification_mapping_version": "2026-06-07",
        "metadata_enrichment": {"status": "succeeded"},
    }
    base.update(overrides)
    return base


class TestBuildExtractionPromptAllowedFields:
    """Test that only allowed fields appear in the prompt."""

    def test_contains_allowed_field_values(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)

        # Allowed fields' values should appear
        assert "attraction" in prompt
        assert "12345" in prompt
        assert "예시 관광지" in prompt
        assert "아름다운 관광지 설명입니다." in prompt
        assert "자연·트레킹" in prompt
        assert "산책로를 따라 걸으세요." in prompt
        assert "09:00~18:00" in prompt
        assert "매주 월요일" in prompt
        assert "무료주차 가능" in prompt
        assert "경상북도 경주시" in prompt

    def test_excludes_forbidden_field_values(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)

        # Forbidden field values should NOT appear in prompt
        assert "CITY#gyeongju" not in prompt
        assert "ATTRACTION#12345" not in prompt
        assert "kr/attractions/12345.json" not in prompt
        assert "s3://lovv-raw-bucket/kr/attractions/12345.json" not in prompt
        assert "classification_source" not in prompt
        assert "classification_mapping_version" not in prompt
        # metadata_enrichment as a section label should not appear
        assert "metadata_enrichment:" not in prompt

    def test_excludes_forbidden_field_keys_from_info_section(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)

        # Forbidden field key names should not appear as info entries
        assert "PK:" not in prompt
        assert "SK:" not in prompt
        assert "source_key:" not in prompt
        assert "raw_s3_uri:" not in prompt


class TestBuildExtractionPromptStructure:
    """Test prompt structure and format."""

    def test_contains_header(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)
        assert "다음 관광지 정보를 분석하여 메타데이터를 추출하세요." in prompt

    def test_contains_info_section(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)
        assert "[관광지 정보]" in prompt

    def test_contains_output_format(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)
        assert "[출력 형식]" in prompt
        assert "indoor_outdoor" in prompt
        assert "vibe_tags" in prompt
        assert "experience_tags" in prompt
        assert "companion_fit" in prompt

    def test_contains_taxonomy(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)
        assert "[허용 태그 목록]" in prompt
        assert "romantic" in prompt
        assert "photo_spot" in prompt
        assert "family" in prompt

    def test_theme_tags_list_joined(self):
        item = _make_attraction_item(theme_tags=["자연·트레킹", "예술·감성"])
        prompt = build_extraction_prompt(item)
        assert "자연·트레킹, 예술·감성" in prompt


class TestBuildExtractionPromptTruncation:
    """Test 12,000 character limit enforcement."""

    def test_prompt_within_limit_for_normal_item(self):
        item = _make_attraction_item()
        prompt = build_extraction_prompt(item)
        assert len(prompt) <= MAX_PROMPT_LENGTH

    def test_prompt_truncates_long_description(self):
        # Create a very long description that would exceed the limit
        long_desc = "가" * 15_000
        item = _make_attraction_item(description=long_desc)
        prompt = build_extraction_prompt(item)
        assert len(prompt) <= MAX_PROMPT_LENGTH

    def test_truncated_prompt_still_has_structure(self):
        long_desc = "나" * 15_000
        item = _make_attraction_item(description=long_desc)
        prompt = build_extraction_prompt(item)

        # Should still contain the header and output format
        assert "다음 관광지 정보를 분석하여 메타데이터를 추출하세요." in prompt
        assert "[출력 형식]" in prompt

    def test_prompt_length_exact_limit(self):
        # Even with extreme input, the result must not exceed MAX_PROMPT_LENGTH
        item = _make_attraction_item(
            description="x" * 20_000,
            experience_guide="y" * 5_000,
            address="z" * 5_000,
        )
        prompt = build_extraction_prompt(item)
        assert len(prompt) <= MAX_PROMPT_LENGTH


class TestBuildExtractionPromptEdgeCases:
    """Test edge cases."""

    def test_empty_item(self):
        item = {}
        prompt = build_extraction_prompt(item)
        assert len(prompt) <= MAX_PROMPT_LENGTH
        assert "[관광지 정보]" in prompt

    def test_none_values_excluded(self):
        item = _make_attraction_item(description=None, parking=None)
        prompt = build_extraction_prompt(item)
        assert "description:" not in prompt
        assert "parking:" not in prompt

    def test_empty_string_values_excluded(self):
        item = _make_attraction_item(description="", parking="")
        prompt = build_extraction_prompt(item)
        assert "description:" not in prompt
        assert "parking:" not in prompt

    def test_empty_list_excluded(self):
        item = _make_attraction_item(theme_tags=[])
        prompt = build_extraction_prompt(item)
        assert "theme_tags:" not in prompt

    def test_extra_unknown_fields_not_included(self):
        item = _make_attraction_item(unknown_field="secret_data")
        prompt = build_extraction_prompt(item)
        assert "secret_data" not in prompt
        assert "unknown_field" not in prompt
