"""
Unit tests for DynamoDBLoader.

Validates Requirements 13.3, 13.6, 13.7.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kr_unified_pipeline.dynamodb_loader import DynamoDBLoader, FailureDetail, LoadResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dynamo_client(*, fail_on_pks: set[str] | None = None) -> MagicMock:
    """Create a mock DynamoDB client.

    Args:
        fail_on_pks: If provided, put_item will raise for items matching these PKs.
    """
    client = MagicMock()
    fail_on_pks = fail_on_pks or set()

    def _put_item(**kwargs: Any) -> dict[str, Any]:
        item = kwargs.get("Item", {})
        # The serialized item uses DynamoDB type descriptors {"S": "value"}
        pk_attr = item.get("PK", {})
        pk_value = pk_attr.get("S", "") if isinstance(pk_attr, dict) else ""
        if pk_value in fail_on_pks:
            raise Exception(f"Simulated write failure for PK={pk_value}")
        return {}

    client.put_item.side_effect = _put_item
    return client


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestDynamoDBLoaderInit:
    """Test loader initialization."""

    def test_stores_table_name(self) -> None:
        client = _make_dynamo_client()
        loader = DynamoDBLoader(client, table_name="TourKoreaDomainDataV2")
        assert loader.table_name == "TourKoreaDomainDataV2"

    def test_stores_custom_table_name(self) -> None:
        client = _make_dynamo_client()
        loader = DynamoDBLoader(client, table_name="MyCustomTable")
        assert loader.table_name == "MyCustomTable"


# ---------------------------------------------------------------------------
# Tests: Successful loading
# ---------------------------------------------------------------------------


class TestDynamoDBLoaderSuccess:
    """Requirement 13.3, 13.6: Write items to DynamoDB."""

    def test_loads_single_item(self) -> None:
        client = _make_dynamo_client()
        loader = DynamoDBLoader(client, table_name="TestTable")

        items = [{"PK": "CITY#Seoul", "SK": "ATTRACTION#001", "title": "Gyeongbokgung"}]
        result = loader.load_items(items)

        assert result.items_loaded == 1
        assert result.items_failed == 0
        assert result.failures == []
        assert client.put_item.call_count == 1

    def test_loads_multiple_items(self) -> None:
        client = _make_dynamo_client()
        loader = DynamoDBLoader(client, table_name="TestTable")

        items = [
            {"PK": "CITY#Seoul", "SK": "ATTRACTION#001", "title": "Palace"},
            {"PK": "CITY#Seoul", "SK": "ATTRACTION#002", "title": "Temple"},
            {"PK": "CITY#Busan", "SK": "FESTIVAL#001", "title": "Film Festival"},
        ]
        result = loader.load_items(items)

        assert result.items_loaded == 3
        assert result.items_failed == 0
        assert client.put_item.call_count == 3

    def test_empty_items_returns_zero_counts(self) -> None:
        client = _make_dynamo_client()
        loader = DynamoDBLoader(client, table_name="TestTable")

        result = loader.load_items([])

        assert result.items_loaded == 0
        assert result.items_failed == 0
        assert result.failures == []
        assert client.put_item.call_count == 0

    def test_passes_correct_table_name_to_put_item(self) -> None:
        client = _make_dynamo_client()
        loader = DynamoDBLoader(client, table_name="TourKoreaDomainDataV2")

        items = [{"PK": "CITY#Test", "SK": "META#city"}]
        loader.load_items(items)

        call_kwargs = client.put_item.call_args[1]
        assert call_kwargs["TableName"] == "TourKoreaDomainDataV2"


# ---------------------------------------------------------------------------
# Tests: Failure handling
# ---------------------------------------------------------------------------


class TestDynamoDBLoaderFailures:
    """Requirement 13.7: Handle failures gracefully, log and continue."""

    def test_continues_on_failure(self) -> None:
        """When one item fails, processing continues for remaining items."""
        client = _make_dynamo_client(fail_on_pks={"CITY#Bad"})
        loader = DynamoDBLoader(client, table_name="TestTable")

        items = [
            {"PK": "CITY#Good1", "SK": "A#001"},
            {"PK": "CITY#Bad", "SK": "A#002"},
            {"PK": "CITY#Good2", "SK": "A#003"},
        ]
        result = loader.load_items(items)

        assert result.items_loaded == 2
        assert result.items_failed == 1
        assert len(result.failures) == 1

    def test_failure_detail_contains_pk_sk(self) -> None:
        """Failure details include the PK and SK of the failed item."""
        client = _make_dynamo_client(fail_on_pks={"CITY#Broken"})
        loader = DynamoDBLoader(client, table_name="TestTable")

        items = [{"PK": "CITY#Broken", "SK": "FESTIVAL#099"}]
        result = loader.load_items(items)

        assert result.items_failed == 1
        failure = result.failures[0]
        assert failure.pk == "CITY#Broken"
        assert failure.sk == "FESTIVAL#099"
        assert "Simulated write failure" in failure.error

    def test_all_items_fail(self) -> None:
        """When all items fail, loaded count is zero."""
        client = _make_dynamo_client(fail_on_pks={"CITY#A", "CITY#B"})
        loader = DynamoDBLoader(client, table_name="TestTable")

        items = [
            {"PK": "CITY#A", "SK": "META"},
            {"PK": "CITY#B", "SK": "META"},
        ]
        result = loader.load_items(items)

        assert result.items_loaded == 0
        assert result.items_failed == 2
        assert len(result.failures) == 2

    def test_missing_pk_sk_uses_unknown(self) -> None:
        """Items without PK/SK fields default to 'UNKNOWN' in failure details."""
        client = MagicMock()
        client.put_item.side_effect = Exception("Network error")

        loader = DynamoDBLoader(client, table_name="TestTable")
        items = [{"title": "No keys here"}]
        result = loader.load_items(items)

        assert result.items_failed == 1
        failure = result.failures[0]
        assert failure.pk == "UNKNOWN"
        assert failure.sk == "UNKNOWN"


# ---------------------------------------------------------------------------
# Tests: LoadResult dataclass
# ---------------------------------------------------------------------------


class TestLoadResult:
    """Test LoadResult structure."""

    def test_default_values(self) -> None:
        result = LoadResult()
        assert result.items_loaded == 0
        assert result.items_failed == 0
        assert result.failures == []

    def test_custom_values(self) -> None:
        failures = [FailureDetail(pk="X", sk="Y", error="err")]
        result = LoadResult(items_loaded=5, items_failed=1, failures=failures)
        assert result.items_loaded == 5
        assert result.items_failed == 1
        assert len(result.failures) == 1


class TestFailureDetail:
    """Test FailureDetail frozen dataclass."""

    def test_creation(self) -> None:
        detail = FailureDetail(pk="CITY#Seoul", sk="ATTR#001", error="timeout")
        assert detail.pk == "CITY#Seoul"
        assert detail.sk == "ATTR#001"
        assert detail.error == "timeout"

    def test_is_frozen(self) -> None:
        detail = FailureDetail(pk="X", sk="Y", error="E")
        with pytest.raises(AttributeError):
            detail.pk = "Z"  # type: ignore[misc]
