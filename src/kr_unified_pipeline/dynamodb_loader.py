"""
DynamoDB loader for the unified pipeline.

Receives pre-processed domain items (from S3ProcessedReader) and writes them
to the New_Domain_Table (TourKoreaDomainDataV2) reusing the existing
`_write_item` and `_coerce_value` helpers from `kr_details_pipeline.load`.

Requirements: 13.3, 13.6, 13.7
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from kr_details_pipeline.load import _coerce_value, _write_item

logger = logging.getLogger(__name__)


class DynamoClientProtocol(Protocol):
    """Minimal DynamoDB client interface required by the loader."""

    def put_item(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class FailureDetail:
    """Details about a single item that failed to load.

    Attributes:
        pk: The item's partition key value.
        sk: The item's sort key value.
        error: Description of the failure.
    """

    pk: str
    sk: str
    error: str


@dataclass(slots=True)
class LoadResult:
    """Result summary for DynamoDB loading operation.

    Attributes:
        items_loaded: Number of items successfully written.
        items_failed: Number of items that failed to write.
        failures: Details of each failed item.
    """

    items_loaded: int = 0
    items_failed: int = 0
    failures: list[FailureDetail] = field(default_factory=list)


class DynamoDBLoader:
    """Loads pre-processed domain items into DynamoDB.

    Reuses `_write_item` from `kr_details_pipeline.load` for the actual
    DynamoDB put_item serialization and write logic.

    Args:
        client: A boto3 DynamoDB client (low-level, not Table resource).
        table_name: Target DynamoDB table name (e.g. "TourKoreaDomainDataV2").
    """

    def __init__(self, client: DynamoClientProtocol, table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    @property
    def table_name(self) -> str:
        return self._table_name

    def load_items(self, items: list[dict[str, Any]]) -> LoadResult:
        """Write a list of domain items to DynamoDB.

        Iterates over each item, calls `_write_item` from the existing
        `kr_details_pipeline.load` module. On failure, logs the error with
        PK/SK, skips the item, and continues processing.

        Args:
            items: List of domain item dicts (as returned by S3ProcessedReader).
                Each dict must contain at least "PK" and "SK" keys.

        Returns:
            LoadResult with counts of loaded/failed items and failure details.
        """
        result = LoadResult()

        for item in items:
            pk = item.get("PK", "UNKNOWN")
            sk = item.get("SK", "UNKNOWN")

            try:
                _write_item(self._client, self._table_name, item)
                result.items_loaded += 1
            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "[DynamoDBLoader] put_item failed PK=%s SK=%s error=%s",
                    pk,
                    sk,
                    error_msg,
                )
                result.items_failed += 1
                result.failures.append(FailureDetail(pk=pk, sk=sk, error=error_msg))

        logger.info(
            "DynamoDB load complete: %d loaded, %d failed (table=%s)",
            result.items_loaded,
            result.items_failed,
            self._table_name,
        )
        return result
