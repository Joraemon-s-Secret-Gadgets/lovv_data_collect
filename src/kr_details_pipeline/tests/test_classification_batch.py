"""Tests for run_classification_batch() in theme_classifier module."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from kr_details_pipeline.theme_classifier import (
    ClassificationBatchResult,
    ThemeClassificationResult,
    run_classification_batch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_festival_item(content_id: str) -> dict[str, Any]:
    """Create a minimal festival item for testing."""
    return {
        "entity_type": "festival",
        "content_id": content_id,
        "title": f"축제 {content_id}",
        "description": "테스트 설명 텍스트입니다. 충분히 긴 설명을 작성합니다.",
    }


def _success_result(*args: Any, **kwargs: Any) -> ThemeClassificationResult:
    return ThemeClassificationResult(
        status="succeeded",
        primary_theme="자연·트레킹",
        theme_tags=["자연·트레킹"],
        festival_theme_classification={"status": "succeeded"},
    )


def _failed_result(*args: Any, **kwargs: Any) -> ThemeClassificationResult:
    return ThemeClassificationResult(
        status="failed",
        primary_theme=None,
        theme_tags=[],
        festival_theme_classification={"status": "failed", "error_code": "timeout"},
    )


def _review_result(*args: Any, **kwargs: Any) -> ThemeClassificationResult:
    return ThemeClassificationResult(
        status="review_required",
        primary_theme=None,
        theme_tags=[],
        festival_theme_classification={"status": "review_required"},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunClassificationBatch:
    """Tests for run_classification_batch()."""

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_all_succeed(self, mock_classify: Any) -> None:
        """All items succeed → success_count matches total."""
        mock_classify.side_effect = _success_result
        items = [_make_festival_item(str(i)) for i in range(5)]

        result = run_classification_batch(None, items)

        assert result.success_count == 5
        assert result.failure_count == 0
        assert result.review_required_count == 0
        assert result.failed_items == []

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_all_failed(self, mock_classify: Any) -> None:
        """All items fail → failure_count matches total, failed_items populated."""
        mock_classify.side_effect = _failed_result
        items = [_make_festival_item(str(i)) for i in range(3)]

        result = run_classification_batch(None, items)

        assert result.success_count == 0
        assert result.failure_count == 3
        assert result.review_required_count == 0
        assert len(result.failed_items) == 3
        assert result.failed_items[0]["content_id"] == "0"
        assert result.failed_items[0]["error_code"] == "timeout"

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_mixed_results(self, mock_classify: Any) -> None:
        """Mix of success, failure, and review_required."""
        mock_classify.side_effect = [
            _success_result(),
            _failed_result(),
            _review_result(),
            _success_result(),
        ]
        items = [_make_festival_item(str(i)) for i in range(4)]

        result = run_classification_batch(None, items)

        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.review_required_count == 1
        assert len(result.failed_items) == 1

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_exception_does_not_halt_batch(self, mock_classify: Any) -> None:
        """Exceptions are caught and processing continues."""
        mock_classify.side_effect = [
            RuntimeError("network error"),
            _success_result(),
            _success_result(),
        ]
        items = [_make_festival_item(str(i)) for i in range(3)]

        result = run_classification_batch(None, items)

        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.failed_items[0]["error_code"] == "unexpected_error"

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_no_split_when_500_or_fewer(self, mock_classify: Any) -> None:
        """Items <= 500 processed as single batch (no splitting)."""
        mock_classify.side_effect = _success_result
        items = [_make_festival_item(str(i)) for i in range(500)]

        result = run_classification_batch(None, items)

        assert result.success_count == 500
        assert mock_classify.call_count == 500

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_split_when_exceeds_500(self, mock_classify: Any) -> None:
        """Items > 500 are split into batches of batch_size."""
        mock_classify.side_effect = _success_result
        items = [_make_festival_item(str(i)) for i in range(501)]

        result = run_classification_batch(None, items, batch_size=100)

        assert result.success_count == 501
        # All items should still be processed
        assert mock_classify.call_count == 501

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_custom_batch_size(self, mock_classify: Any) -> None:
        """Custom batch_size is respected when items > 500."""
        mock_classify.side_effect = _success_result
        items = [_make_festival_item(str(i)) for i in range(550)]

        result = run_classification_batch(None, items, batch_size=50)

        assert result.success_count == 550
        assert mock_classify.call_count == 550

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_empty_items_list(self, mock_classify: Any) -> None:
        """Empty list returns zero counts."""
        result = run_classification_batch(None, [])

        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.review_required_count == 0
        assert result.failed_items == []
        mock_classify.assert_not_called()

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_failure_in_middle_continues_processing(self, mock_classify: Any) -> None:
        """A failure in the middle of a batch doesn't stop remaining items."""
        mock_classify.side_effect = [
            _success_result(),
            _success_result(),
            RuntimeError("something broke"),
            _success_result(),
            _success_result(),
        ]
        items = [_make_festival_item(str(i)) for i in range(5)]

        result = run_classification_batch(None, items)

        assert result.success_count == 4
        assert result.failure_count == 1
        assert result.failed_items[0]["content_id"] == "2"

    @patch("kr_details_pipeline.theme_classifier.classify_festival_theme")
    def test_model_id_and_prompt_version_passed_through(
        self, mock_classify: Any
    ) -> None:
        """Custom model_id and prompt_version are passed to classify_festival_theme."""
        mock_classify.side_effect = _success_result
        items = [_make_festival_item("1")]

        run_classification_batch(
            "fake_client",
            items,
            model_id="custom-model",
            prompt_version="v2",
        )

        mock_classify.assert_called_once_with(
            "fake_client",
            items[0],
            model_id="custom-model",
            prompt_version="v2",
        )
