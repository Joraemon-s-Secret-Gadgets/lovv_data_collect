"""Tests for enrichment_engine: enrich_attraction() function.

Validates Bedrock converse API integration, retry logic, error handling,
metadata_enrichment history object construction, and all-unknown/empty skip logic.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from kr_details_pipeline.enrichment_engine import (
    DEFAULT_MODEL_ID,
    MAX_RETRIES,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    EnrichmentResult,
    enrich_attraction,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_attraction_item(**overrides: Any) -> dict[str, Any]:
    """Create a minimal valid attraction item for testing."""
    base = {
        "entity_type": "attraction",
        "content_id": "12345",
        "title": "테스트 관광지",
        "description": "아름다운 산책로",
        "theme": "자연·트레킹",
        "theme_tags": ["자연·트레킹"],
        "experience_guide": "등산 코스",
        "opening_hours": "09:00~18:00",
        "closed_days": "매주 월요일",
        "parking": "무료주차",
        "address": "경상북도 테스트시",
        "PK": "CITY#test",
        "SK": "ATTRACTION#12345",
    }
    base.update(overrides)
    return base


def _make_bedrock_response(
    indoor_outdoor: str = "outdoor",
    vibe_tags: list[str] | None = None,
    experience_tags: list[str] | None = None,
    companion_fit: list[str] | None = None,
) -> dict[str, Any]:
    """Create a mock Bedrock converse API response."""
    payload = {
        "indoor_outdoor": indoor_outdoor,
        "vibe_tags": vibe_tags or ["refreshing", "mountain_view"],
        "experience_tags": experience_tags or ["walking"],
        "companion_fit": companion_fit or ["family", "couple"],
    }
    return {
        "output": {
            "message": {
                "content": [{"text": json.dumps(payload)}]
            }
        }
    }


def _make_client_error(code: str = "InternalServerError") -> ClientError:
    """Create a botocore ClientError with the given error code."""
    return ClientError(
        {"Error": {"Code": code, "Message": "Test error"}},
        "Converse",
    )


# ---------------------------------------------------------------------------
# entity_type filtering (Req 3.1)
# ---------------------------------------------------------------------------


class TestEntityTypeFilter:
    """Only entity_type='attraction' items should be processed."""

    def test_non_attraction_returns_failed(self):
        client = MagicMock()
        item = _make_attraction_item(entity_type="festival")

        result = enrich_attraction(client, item)

        assert result.status == "failed"
        assert result.metadata_enrichment["status"] == "failed"
        assert result.metadata_enrichment["error_code"] == "model_error"
        assert "failed_at" in result.metadata_enrichment
        client.converse.assert_not_called()

    def test_missing_entity_type_returns_failed(self):
        client = MagicMock()
        item = _make_attraction_item()
        del item["entity_type"]

        result = enrich_attraction(client, item)

        assert result.status == "failed"
        client.converse.assert_not_called()

    def test_attraction_entity_type_proceeds(self):
        client = MagicMock()
        client.converse.return_value = _make_bedrock_response()
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "succeeded"
        client.converse.assert_called_once()


# ---------------------------------------------------------------------------
# Skip logic (Req 4.4, 4.5, 4.6)
# ---------------------------------------------------------------------------


class TestSkipEnrichment:
    """Items with matching hash/version/model should be skipped."""

    def test_skip_when_already_succeeded_with_same_hash(self):
        client = MagicMock()
        item = _make_attraction_item()

        # Compute the hash for this item and set up succeeded enrichment
        from kr_details_pipeline.enrichment_engine import compute_input_hash

        current_hash = compute_input_hash(item)
        item["metadata_enrichment"] = {
            "status": "succeeded",
            "input_hash": current_hash,
            "prompt_version": PROMPT_VERSION,
            "model_id": DEFAULT_MODEL_ID,
        }

        result = enrich_attraction(client, item)

        assert result.status == "skipped"
        client.converse.assert_not_called()

    def test_no_skip_when_hash_differs(self):
        client = MagicMock()
        client.converse.return_value = _make_bedrock_response()
        item = _make_attraction_item()
        item["metadata_enrichment"] = {
            "status": "succeeded",
            "input_hash": "sha256:different_hash",
            "prompt_version": PROMPT_VERSION,
            "model_id": DEFAULT_MODEL_ID,
        }

        result = enrich_attraction(client, item)

        assert result.status == "succeeded"
        client.converse.assert_called_once()

    def test_no_skip_when_previous_failed(self):
        client = MagicMock()
        client.converse.return_value = _make_bedrock_response()
        item = _make_attraction_item()

        from kr_details_pipeline.enrichment_engine import compute_input_hash

        current_hash = compute_input_hash(item)
        item["metadata_enrichment"] = {
            "status": "failed",
            "input_hash": current_hash,
            "prompt_version": PROMPT_VERSION,
            "model_id": DEFAULT_MODEL_ID,
        }

        result = enrich_attraction(client, item)

        assert result.status == "succeeded"
        client.converse.assert_called_once()


# ---------------------------------------------------------------------------
# Successful enrichment (Req 4.1)
# ---------------------------------------------------------------------------


class TestSuccessfulEnrichment:
    """On success, metadata_enrichment should have proper fields."""

    def test_success_returns_extracted_fields(self):
        client = MagicMock()
        client.converse.return_value = _make_bedrock_response(
            indoor_outdoor="outdoor",
            vibe_tags=["refreshing", "mountain_view"],
            experience_tags=["walking", "photo_spot"],
            companion_fit=["family", "couple", "solo"],
        )
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "succeeded"
        assert result.indoor_outdoor == "outdoor"
        assert result.vibe_tags == ["refreshing", "mountain_view"]
        assert result.experience_tags == ["walking", "photo_spot"]
        assert result.companion_fit == ["family", "couple", "solo"]

    def test_success_metadata_enrichment_fields(self):
        client = MagicMock()
        client.converse.return_value = _make_bedrock_response()
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        me = result.metadata_enrichment
        assert me["status"] == "succeeded"
        assert me["model_id"] == DEFAULT_MODEL_ID
        assert me["prompt_version"] == PROMPT_VERSION
        assert me["schema_version"] == SCHEMA_VERSION
        assert "generated_at" in me
        assert "input_hash" in me
        assert me["input_hash"].startswith("sha256:")

    def test_item_dict_not_modified(self):
        """Req 5.3: enrich_attraction must not modify the input item."""
        client = MagicMock()
        client.converse.return_value = _make_bedrock_response()
        item = _make_attraction_item()
        original_item = item.copy()

        enrich_attraction(client, item)

        assert item == original_item


# ---------------------------------------------------------------------------
# All-unknown/empty → skipped (Req 4.3)
# ---------------------------------------------------------------------------


class TestAllUnknownSkipped:
    """If all 4 outputs are unknown/empty, status should be 'skipped'."""

    def test_all_unknown_returns_skipped(self):
        client = MagicMock()
        payload = {
            "indoor_outdoor": "unknown",
            "vibe_tags": [],
            "experience_tags": [],
            "companion_fit": [],
        }
        client.converse.return_value = {
            "output": {"message": {"content": [{"text": json.dumps(payload)}]}}
        }
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "skipped"
        assert result.metadata_enrichment["status"] == "skipped"
        assert "input_hash" in result.metadata_enrichment

    def test_one_valid_tag_not_skipped(self):
        client = MagicMock()
        payload = {
            "indoor_outdoor": "unknown",
            "vibe_tags": ["calm"],
            "experience_tags": [],
            "companion_fit": [],
        }
        client.converse.return_value = {
            "output": {"message": {"content": [{"text": json.dumps(payload)}]}}
        }
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Retry logic (Req 3.10, 5.4)
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Bedrock call retries on network/service errors, max 2 retries."""

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_retries_on_throttling(self, mock_sleep):
        client = MagicMock()
        # First call fails with throttling, second succeeds
        client.converse.side_effect = [
            _make_client_error("ThrottlingException"),
            _make_bedrock_response(),
        ]
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "succeeded"
        assert client.converse.call_count == 2
        mock_sleep.assert_called_once_with(1.0)  # first retry: 1s delay

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_retries_on_timeout(self, mock_sleep):
        client = MagicMock()
        # First two calls fail, third succeeds
        client.converse.side_effect = [
            _make_client_error("ModelTimeoutException"),
            _make_client_error("ModelTimeoutException"),
            _make_bedrock_response(),
        ]
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "succeeded"
        assert client.converse.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_all_retries_exhausted_returns_failed(self, mock_sleep):
        client = MagicMock()
        # All 3 attempts (initial + 2 retries) fail
        client.converse.side_effect = [
            _make_client_error("InternalServerError"),
            _make_client_error("InternalServerError"),
            _make_client_error("InternalServerError"),
        ]
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "failed"
        assert result.metadata_enrichment["status"] == "failed"
        assert result.metadata_enrichment["error_code"] == "model_error"
        assert "failed_at" in result.metadata_enrichment
        assert client.converse.call_count == 3

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep):
        client = MagicMock()
        client.converse.side_effect = [
            _make_client_error("ThrottlingException"),
            _make_client_error("ThrottlingException"),
            _make_bedrock_response(),
        ]
        item = _make_attraction_item()

        enrich_attraction(client, item)

        # Verify exponential backoff: 1s, 2s
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0


# ---------------------------------------------------------------------------
# Error categorization
# ---------------------------------------------------------------------------


class TestErrorCategorization:
    """ClientError codes map to correct enrichment error_codes."""

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_throttling_error_code(self, mock_sleep):
        client = MagicMock()
        client.converse.side_effect = _make_client_error("ThrottlingException")
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.metadata_enrichment["error_code"] == "throttling"

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_timeout_error_code(self, mock_sleep):
        client = MagicMock()
        client.converse.side_effect = _make_client_error("ModelTimeoutException")
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.metadata_enrichment["error_code"] == "timeout"

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_generic_service_error_becomes_model_error(self, mock_sleep):
        client = MagicMock()
        client.converse.side_effect = _make_client_error("ServiceUnavailable")
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.metadata_enrichment["error_code"] == "model_error"


# ---------------------------------------------------------------------------
# Validation errors (Req 5.2) — no retry
# ---------------------------------------------------------------------------


class TestValidationErrors:
    """JSON parse or schema validation errors fail immediately without retry."""

    def test_invalid_json_returns_validation_error(self):
        client = MagicMock()
        client.converse.return_value = {
            "output": {"message": {"content": [{"text": "not valid json"}]}}
        }
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "failed"
        assert result.metadata_enrichment["error_code"] == "validation_error"
        # No retry: only one call
        client.converse.assert_called_once()

    def test_extra_fields_returns_validation_error(self):
        client = MagicMock()
        payload = {
            "indoor_outdoor": "outdoor",
            "vibe_tags": ["calm"],
            "experience_tags": ["walking"],
            "companion_fit": ["family"],
            "unexpected_field": "bad",
        }
        client.converse.return_value = {
            "output": {"message": {"content": [{"text": json.dumps(payload)}]}}
        }
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "failed"
        assert result.metadata_enrichment["error_code"] == "validation_error"
        client.converse.assert_called_once()


# ---------------------------------------------------------------------------
# Failure preservation (Req 5.1)
# ---------------------------------------------------------------------------


class TestFailurePreservation:
    """On failure, only metadata_enrichment is populated, no derived fields."""

    @patch("kr_details_pipeline.enrichment_engine.time.sleep")
    def test_failed_result_has_no_derived_fields(self, mock_sleep):
        client = MagicMock()
        client.converse.side_effect = _make_client_error("InternalServerError")
        item = _make_attraction_item()

        result = enrich_attraction(client, item)

        assert result.status == "failed"
        assert result.indoor_outdoor is None
        assert result.vibe_tags == []
        assert result.experience_tags == []
        assert result.companion_fit == []
