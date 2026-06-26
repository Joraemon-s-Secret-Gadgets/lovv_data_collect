"""Tests for gsi_query: query_festivals_by_month()."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kr_details_pipeline.gsi_query import query_festivals_by_month


# ---------------------------------------------------------------------------
# Helper: mock DynamoDB client
# ---------------------------------------------------------------------------


def _make_mock_client(pages: list[dict[str, Any]]) -> MagicMock:
    """Create a mock DynamoDB client that returns given pages from query()."""
    client = MagicMock()
    client.query.side_effect = pages
    return client


# ---------------------------------------------------------------------------
# KeyConditionExpression construction (Req 10.3, 10.4)
# ---------------------------------------------------------------------------


class TestKeyConditionExpression:
    """Verify KeyConditionExpression uses entity_type + gsi_sk prefix."""

    def test_key_condition_uses_entity_type_and_begins_with(self):
        client = _make_mock_client([{"Items": [], "Count": 0}])
        query_festivals_by_month(client, "TestTable", "FestivalMonthIndex", 10)

        call_kwargs = client.query.call_args[1]
        assert call_kwargs["KeyConditionExpression"] == (
            "entity_type = :et AND begins_with(gsi_sk, :prefix)"
        )
        assert call_kwargs["ExpressionAttributeValues"][":et"] == {"S": "festival"}

    def test_index_name_passed_correctly(self):
        client = _make_mock_client([{"Items": [], "Count": 0}])
        query_festivals_by_month(client, "MyTable", "CustomGSI", 5)

        call_kwargs = client.query.call_args[1]
        assert call_kwargs["TableName"] == "MyTable"
        assert call_kwargs["IndexName"] == "CustomGSI"


# ---------------------------------------------------------------------------
# Month prefix formatting (Req 10.2)
# ---------------------------------------------------------------------------


class TestMonthPrefixFormatting:
    """Month prefix must be zero-padded 2-digit in FESTIVAL#{mm} format."""

    @pytest.mark.parametrize(
        "month,expected_prefix",
        [
            (1, "FESTIVAL#01"),
            (2, "FESTIVAL#02"),
            (9, "FESTIVAL#09"),
            (10, "FESTIVAL#10"),
            (11, "FESTIVAL#11"),
            (12, "FESTIVAL#12"),
            (0, "FESTIVAL#00"),
        ],
    )
    def test_month_prefix_formatting(self, month: int, expected_prefix: str):
        client = _make_mock_client([{"Items": [], "Count": 0}])
        query_festivals_by_month(client, "T", "I", month)

        call_kwargs = client.query.call_args[1]
        prefix_value = call_kwargs["ExpressionAttributeValues"][":prefix"]["S"]
        assert prefix_value == expected_prefix


# ---------------------------------------------------------------------------
# Pagination handling
# ---------------------------------------------------------------------------


class TestPaginationHandling:
    """Query must handle multi-page responses correctly."""

    def test_single_page_returns_items(self):
        items = [{"PK": {"S": "CITY#seoul"}, "SK": {"S": "FESTIVAL#1001"}}]
        client = _make_mock_client([{"Items": items, "Count": 1}])

        result = query_festivals_by_month(client, "T", "I", 10)
        assert result == items
        assert client.query.call_count == 1

    def test_multi_page_aggregates_all_items(self):
        page1_items = [{"PK": {"S": "CITY#seoul"}, "SK": {"S": "FESTIVAL#1001"}}]
        page2_items = [{"PK": {"S": "CITY#busan"}, "SK": {"S": "FESTIVAL#2002"}}]
        page3_items = [{"PK": {"S": "CITY#jeju"}, "SK": {"S": "FESTIVAL#3003"}}]

        pages = [
            {"Items": page1_items, "Count": 1, "LastEvaluatedKey": {"pk": "k1"}},
            {"Items": page2_items, "Count": 1, "LastEvaluatedKey": {"pk": "k2"}},
            {"Items": page3_items, "Count": 1},
        ]
        client = _make_mock_client(pages)

        result = query_festivals_by_month(client, "T", "I", 10)
        assert len(result) == 3
        assert result == page1_items + page2_items + page3_items
        assert client.query.call_count == 3

    def test_pagination_passes_exclusive_start_key(self):
        last_key = {"entity_type": {"S": "festival"}, "gsi_sk": {"S": "FESTIVAL#10#1001"}}
        pages = [
            {"Items": [{"id": "1"}], "Count": 1, "LastEvaluatedKey": last_key},
            {"Items": [{"id": "2"}], "Count": 1},
        ]
        client = _make_mock_client(pages)

        query_festivals_by_month(client, "T", "I", 10)

        # Second call should include ExclusiveStartKey
        second_call_kwargs = client.query.call_args_list[1][1]
        assert second_call_kwargs["ExclusiveStartKey"] == last_key

    def test_empty_items_list_no_pagination(self):
        client = _make_mock_client([{"Items": [], "Count": 0}])

        result = query_festivals_by_month(client, "T", "I", 3)
        assert result == []
        assert client.query.call_count == 1


# ---------------------------------------------------------------------------
# Optional classification_status filter (Req 10.7)
# ---------------------------------------------------------------------------


class TestClassificationStatusFilter:
    """Filter by festival_theme_classification.status when specified."""

    def test_default_filters_by_succeeded(self):
        client = _make_mock_client([{"Items": [], "Count": 0}])
        query_festivals_by_month(client, "T", "I", 5)

        call_kwargs = client.query.call_args[1]
        assert "FilterExpression" in call_kwargs
        assert call_kwargs["FilterExpression"] == (
            "festival_theme_classification.#st = :status"
        )
        assert call_kwargs["ExpressionAttributeNames"] == {"#st": "status"}
        assert call_kwargs["ExpressionAttributeValues"][":status"] == {"S": "succeeded"}

    def test_custom_status_filter(self):
        client = _make_mock_client([{"Items": [], "Count": 0}])
        query_festivals_by_month(client, "T", "I", 7, classification_status="failed")

        call_kwargs = client.query.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == {"S": "failed"}

    def test_none_status_skips_filter(self):
        client = _make_mock_client([{"Items": [], "Count": 0}])
        query_festivals_by_month(client, "T", "I", 8, classification_status=None)

        call_kwargs = client.query.call_args[1]
        assert "FilterExpression" not in call_kwargs
        assert "ExpressionAttributeNames" not in call_kwargs
        # Only :et and :prefix should be in expression values
        assert ":status" not in call_kwargs["ExpressionAttributeValues"]


# ---------------------------------------------------------------------------
# PK/SK structure preservation (Req 10.3)
# ---------------------------------------------------------------------------


class TestPkSkPreservation:
    """GSI query uses entity_type as PK and gsi_sk as SK — not main table PK/SK."""

    def test_query_does_not_reference_main_pk_sk(self):
        """Ensure the query uses GSI keys, not CITY#/FESTIVAL# main table keys."""
        client = _make_mock_client([{"Items": [], "Count": 0}])
        query_festivals_by_month(client, "T", "I", 10)

        call_kwargs = client.query.call_args[1]
        key_condition = call_kwargs["KeyConditionExpression"]
        # Should reference entity_type and gsi_sk, NOT PK or SK
        assert "entity_type" in key_condition
        assert "gsi_sk" in key_condition
        assert "PK" not in key_condition
        assert "SK" not in key_condition
