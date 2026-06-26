"""Unit tests for classify_festival_theme() function."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kr_details_pipeline.theme_classifier import (
    DEFAULT_MODEL_ID,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ThemeClassificationResult,
    classify_festival_theme,
    compute_festival_input_hash,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_festival_item(
    *,
    content_id: str = "2002",
    description: str = "한탄강 얼음 위를 걸으며 겨울의 아름다움을 느끼는 축제입니다",
    program: str = "얼음트레킹, 빙벽체험, 얼음낚시, 빙어잡기",
    subevent: str = "먹거리장터, 불꽃놀이",
    title: str = "철원 한탄강 얼음트레킹 축제",
    entity_type: str = "festival",
    source_theme: str = "예술·감성",
    lcls_systm3: str = "EV010100",
    theme: str | None = None,
    theme_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Create a festival item with sufficient text for classification."""
    item: dict[str, Any] = {
        "entity_type": entity_type,
        "content_id": content_id,
        "title": title,
        "description": description,
        "program": program,
        "subevent": subevent,
        "venue": "한탄강 일대",
        "playtime": "10:00~17:00",
        "lcls_systm3": lcls_systm3,
        "source_theme": source_theme,
        "source_subtype_name": "문화관광축제",
    }
    if theme is not None:
        item["theme"] = theme
    if theme_tags is not None:
        item["theme_tags"] = theme_tags
    return item


def _make_bedrock_response(
    primary_theme: str = "자연·트레킹",
    theme_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Create a Bedrock converse API response structure."""
    if theme_tags is None:
        theme_tags = [primary_theme]
    payload = {"primary_theme": primary_theme, "theme_tags": theme_tags}
    return {
        "output": {
            "message": {
                "content": [{"text": json.dumps(payload, ensure_ascii=False)}]
            }
        }
    }


def _make_client(response: dict[str, Any] | None = None) -> MagicMock:
    """Create a mock Bedrock client."""
    client = MagicMock()
    if response is not None:
        client.converse.return_value = response
    return client


# ---------------------------------------------------------------------------
# Test: entity_type filter (Step 1)
# ---------------------------------------------------------------------------


class TestEntityTypeFilter:
    """classify_festival_theme only processes festival items."""

    def test_non_festival_returns_failed(self) -> None:
        """Non-festival entity_type returns failed result immediately."""
        item = _make_festival_item(entity_type="attraction")
        client = _make_client()

        result = classify_festival_theme(client, item)

        assert result.status == "failed"
        assert result.festival_theme_classification["error_code"] == "invalid_entity_type"
        client.converse.assert_not_called()

    def test_missing_entity_type_returns_failed(self) -> None:
        """Missing entity_type returns failed result."""
        item = _make_festival_item()
        del item["entity_type"]
        client = _make_client()

        result = classify_festival_theme(client, item)

        assert result.status == "failed"
        assert result.festival_theme_classification["error_code"] == "invalid_entity_type"


# ---------------------------------------------------------------------------
# Test: Skip logic (Step 2)
# ---------------------------------------------------------------------------


class TestSkipClassification:
    """Already-classified items with matching hash should be skipped."""

    def test_skip_when_already_succeeded_with_same_hash(self) -> None:
        """Items with succeeded + matching hash/prompt/model skip Bedrock."""
        item = _make_festival_item(theme="자연·트레킹", theme_tags=["자연·트레킹"])
        input_hash = compute_festival_input_hash(item)
        item["festival_theme_classification"] = {
            "status": "succeeded",
            "input_hash": input_hash,
            "prompt_version": PROMPT_VERSION,
            "model_id": DEFAULT_MODEL_ID,
        }
        client = _make_client()

        result = classify_festival_theme(client, item)

        assert result.status == "succeeded"
        assert result.primary_theme == "자연·트레킹"
        assert result.theme_tags == ["자연·트레킹"]
        client.converse.assert_not_called()

    def test_no_skip_when_status_is_failed(self) -> None:
        """Items with failed status are re-processed."""
        item = _make_festival_item()
        input_hash = compute_festival_input_hash(item)
        item["festival_theme_classification"] = {
            "status": "failed",
            "input_hash": input_hash,
            "prompt_version": PROMPT_VERSION,
            "model_id": DEFAULT_MODEL_ID,
        }
        client = _make_client(_make_bedrock_response())

        result = classify_festival_theme(client, item)

        assert result.status == "succeeded"
        client.converse.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Text sufficiency (Step 3)
# ---------------------------------------------------------------------------


class TestTextSufficiency:
    """Items with insufficient text return review_required."""

    def test_all_text_fields_short_returns_review_required(self) -> None:
        """All text fields < 30 chars → review_required."""
        item = _make_festival_item(
            description="짧음",  # < 30 chars
            program="짧",
            subevent="짧",
        )
        client = _make_client()

        result = classify_festival_theme(client, item)

        assert result.status == "review_required"
        assert result.festival_theme_classification["status"] == "review_required"
        assert "input_hash" in result.festival_theme_classification
        client.converse.assert_not_called()

    def test_empty_text_fields_returns_review_required(self) -> None:
        """All empty text fields → review_required."""
        item = _make_festival_item(description="", program="", subevent="")
        client = _make_client()

        result = classify_festival_theme(client, item)

        assert result.status == "review_required"
        client.converse.assert_not_called()

    def test_one_sufficient_field_proceeds(self) -> None:
        """At least one field >= 30 chars → proceed to Bedrock call."""
        item = _make_festival_item(
            description="이 축제는 30자가 넘는 충분히 긴 설명 텍스트를 가지고 있습니다",
            program="짧",
            subevent="",
        )
        client = _make_client(_make_bedrock_response())

        result = classify_festival_theme(client, item)

        assert result.status == "succeeded"
        client.converse.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Successful classification (Steps 5-7)
# ---------------------------------------------------------------------------


class TestSuccessfulClassification:
    """Successful Bedrock calls produce correct results."""

    def test_success_returns_validated_theme(self) -> None:
        """Successful call returns primary_theme and theme_tags."""
        item = _make_festival_item()
        response = _make_bedrock_response("자연·트레킹", ["자연·트레킹", "온천·휴양"])
        client = _make_client(response)

        result = classify_festival_theme(client, item)

        assert result.status == "succeeded"
        assert result.primary_theme == "자연·트레킹"
        assert result.theme_tags == ["자연·트레킹", "온천·휴양"]

    def test_success_builds_history_object(self) -> None:
        """History object has required fields on success."""
        item = _make_festival_item()
        client = _make_client(_make_bedrock_response())

        result = classify_festival_theme(client, item)

        hist = result.festival_theme_classification
        assert hist["status"] == "succeeded"
        assert hist["model_id"] == DEFAULT_MODEL_ID
        assert hist["prompt_version"] == PROMPT_VERSION
        assert hist["schema_version"] == SCHEMA_VERSION
        assert "generated_at" in hist
        assert "input_hash" in hist
        assert hist["input_hash"].startswith("sha256:")

    def test_success_preserves_source_fields_in_result(self) -> None:
        """On success, result does not modify source fields - the function
        only returns ThemeClassificationResult, not modifying item dict."""
        item = _make_festival_item(source_theme="예술·감성")
        client = _make_client(_make_bedrock_response("자연·트레킹"))

        result = classify_festival_theme(client, item)

        # The function returns the new theme, doesn't modify the item
        assert result.primary_theme == "자연·트레킹"
        # Original item's source fields remain unchanged
        assert item["source_theme"] == "예술·감성"
        assert item["source_subtype_name"] == "문화관광축제"
        assert item["lcls_systm3"] == "EV010100"

    def test_markdown_fenced_json_is_parsed(self) -> None:
        """Bedrock response wrapped in markdown code fences is handled."""
        item = _make_festival_item()
        payload = '```json\n{"primary_theme": "바다·해안", "theme_tags": ["바다·해안"]}\n```'
        response = {"output": {"message": {"content": [{"text": payload}]}}}
        client = _make_client(response)

        result = classify_festival_theme(client, item)

        assert result.status == "succeeded"
        assert result.primary_theme == "바다·해안"


# ---------------------------------------------------------------------------
# Test: Failure handling (Step 8)
# ---------------------------------------------------------------------------


class TestFailureHandling:
    """Failures build appropriate history and don't modify theme."""

    def test_invalid_json_returns_validation_error(self) -> None:
        """Non-JSON Bedrock response → validation_error, no retry."""
        item = _make_festival_item()
        response = {"output": {"message": {"content": [{"text": "not json"}]}}}
        client = _make_client(response)

        result = classify_festival_theme(client, item)

        assert result.status == "failed"
        assert result.festival_theme_classification["error_code"] == "validation_error"
        # validation_error should not retry
        assert client.converse.call_count == 1

    def test_invalid_theme_returns_validation_error(self) -> None:
        """Invalid primary_theme → validation_error via ThemeValidationError."""
        item = _make_festival_item()
        payload = json.dumps({"primary_theme": "없는테마", "theme_tags": ["없는테마"]})
        response = {"output": {"message": {"content": [{"text": payload}]}}}
        client = _make_client(response)

        result = classify_festival_theme(client, item)

        assert result.status == "failed"
        assert result.festival_theme_classification["error_code"] == "validation_error"
        assert client.converse.call_count == 1

    def test_throttling_retries_and_fails(self) -> None:
        """ThrottlingException triggers retries then fails."""
        item = _make_festival_item()
        exc = Exception("ThrottlingException: rate limit exceeded")
        client = MagicMock()
        client.converse.side_effect = exc

        with patch("kr_details_pipeline.theme_classifier.time.sleep"):
            result = classify_festival_theme(client, item)

        assert result.status == "failed"
        assert result.festival_theme_classification["error_code"] == "throttling"
        # Initial attempt + MAX_RETRIES (2) = 3 total attempts
        assert client.converse.call_count == 3

    def test_timeout_retries_and_fails(self) -> None:
        """Timeout errors trigger retries."""
        item = _make_festival_item()
        exc = Exception("ModelTimeoutException: request timed out")
        client = MagicMock()
        client.converse.side_effect = exc

        with patch("kr_details_pipeline.theme_classifier.time.sleep"):
            result = classify_festival_theme(client, item)

        assert result.status == "failed"
        assert result.festival_theme_classification["error_code"] == "timeout"
        assert client.converse.call_count == 3

    def test_model_error_retries_and_fails(self) -> None:
        """Generic model errors trigger retries."""
        item = _make_festival_item()
        exc = RuntimeError("InternalServerError")
        client = MagicMock()
        client.converse.side_effect = exc

        with patch("kr_details_pipeline.theme_classifier.time.sleep"):
            result = classify_festival_theme(client, item)

        assert result.status == "failed"
        assert result.festival_theme_classification["error_code"] == "model_error"
        assert client.converse.call_count == 3

    def test_failure_does_not_auto_promote_source_theme(self) -> None:
        """On failure, source_theme is NOT promoted to theme (Req 8.3)."""
        item = _make_festival_item(
            source_theme="예술·감성",
            theme="역사·전통",
            theme_tags=["역사·전통"],
        )
        response = {"output": {"message": {"content": [{"text": "invalid"}]}}}
        client = _make_client(response)

        result = classify_festival_theme(client, item)

        assert result.status == "failed"
        # Result should NOT contain source_theme as primary_theme
        assert result.primary_theme is None
        # Original item values should remain unchanged
        assert item["theme"] == "역사·전통"
        assert item["theme_tags"] == ["역사·전통"]
        assert item["source_theme"] == "예술·감성"

    def test_failure_history_has_required_fields(self) -> None:
        """Failure history has status, error_code, model_id, etc."""
        item = _make_festival_item()
        response = {"output": {"message": {"content": [{"text": "bad"}]}}}
        client = _make_client(response)

        result = classify_festival_theme(client, item)

        hist = result.festival_theme_classification
        assert hist["status"] == "failed"
        assert hist["error_code"] == "validation_error"
        assert hist["model_id"] == DEFAULT_MODEL_ID
        assert hist["prompt_version"] == PROMPT_VERSION
        assert hist["schema_version"] == SCHEMA_VERSION
        assert "failed_at" in hist
        assert "input_hash" in hist

    def test_retry_then_success(self) -> None:
        """Retryable error followed by success → succeeded."""
        item = _make_festival_item()
        exc = Exception("ThrottlingException: rate limit")
        success_response = _make_bedrock_response("미식·노포", ["미식·노포"])
        client = MagicMock()
        client.converse.side_effect = [exc, success_response]

        with patch("kr_details_pipeline.theme_classifier.time.sleep"):
            result = classify_festival_theme(client, item)

        assert result.status == "succeeded"
        assert result.primary_theme == "미식·노포"
        assert client.converse.call_count == 2
