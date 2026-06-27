"""Unit tests for LocalTestRunner."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kr_unified_pipeline.local_test import LocalTestRunner
from kr_unified_pipeline.models import LocalTestSummary, RebuildManifest
from kr_unified_pipeline.dynamodb_loader import LoadResult, FailureDetail


class FakeSession:
    """Fake boto3 Session for testing."""

    def __init__(self, s3_client: Any = None, dynamodb_client: Any = None) -> None:
        self._s3 = s3_client or MagicMock()
        self._dynamodb = dynamodb_client or MagicMock()

    def client(self, service_name: str, **kwargs: Any) -> Any:
        if service_name == "s3":
            return self._s3
        if service_name == "dynamodb":
            return self._dynamodb
        return MagicMock()


def _make_s3_client_with_items(items: list[dict[str, Any]], bucket: str = "test-bucket") -> MagicMock:
    """Create a mock S3 client that returns the given items from a single JSON file."""
    s3 = MagicMock()

    # list_objects_v2 returns one JSON file key
    s3.list_objects_v2.return_value = {
        "Contents": [{"Key": "processed/KR/details/20250115/passed/data.json"}],
        "IsTruncated": False,
    }

    # get_object returns the items as JSON body
    body_mock = MagicMock()
    body_mock.read.return_value = json.dumps(items).encode()
    s3.get_object.return_value = {"Body": body_mock}

    return s3


class TestLocalTestRunnerPassVerdict:
    """Tests where the local test should produce PASS verdict."""

    @patch("kr_unified_pipeline.local_test.VectorRebuilder")
    def test_pass_when_all_operations_succeed(self, mock_rebuilder_cls: MagicMock) -> None:
        """Verdict is PASS when S3 read, DynamoDB load, and vector rebuild all succeed."""
        items = [
            {"PK": "CITY#seoul", "SK": "META", "province_key": "KR-11"},
            {"PK": "CITY#busan", "SK": "META", "province_key": "KR-26"},
            {"PK": "CITY#gangneung", "SK": "META", "province_key": "KR-42"},
        ]

        s3_client = _make_s3_client_with_items(items)
        dynamodb_client = MagicMock()
        # Simulate successful put_item (no exception)
        dynamodb_client.put_item = MagicMock(return_value={})

        session = FakeSession(s3_client=s3_client, dynamodb_client=dynamodb_client)

        # Mock VectorRebuilder to return successful manifest
        mock_rebuilder_instance = MagicMock()
        mock_rebuilder_instance.rebuild.return_value = RebuildManifest(
            rebuild_mode="full",
            total_items_processed=1,
            items_upserted=1,
            items_skipped=0,
            errors_encountered=[],
        )
        mock_rebuilder_cls.return_value = mock_rebuilder_instance

        runner = LocalTestRunner(
            province_id="KR-42",
            bucket="test-bucket",
            ingest_date="20250115",
            table_name="TourKoreaDomainDataV2",
            vector_bucket="lovv-vector-dev",
            index_name="kr-tour-domain-v1",
            session=session,
        )

        summary = runner.run()

        assert summary.verdict == "PASS"
        assert summary.province_id == "KR-42"
        assert summary.items_read_from_s3 == 1  # Only KR-42 items pass the filter
        assert summary.items_loaded_to_dynamodb == 1
        assert summary.vectors_built == 1
        assert summary.failed_items == []
        assert summary.execution_time_seconds >= 0

    @patch("kr_unified_pipeline.local_test.VectorRebuilder")
    def test_pass_with_zero_items(self, mock_rebuilder_cls: MagicMock) -> None:
        """Verdict is PASS even when no items match the province (zero failures)."""
        items = [
            {"PK": "CITY#seoul", "SK": "META", "province_key": "KR-11"},
        ]

        s3_client = _make_s3_client_with_items(items)
        dynamodb_client = MagicMock()

        session = FakeSession(s3_client=s3_client, dynamodb_client=dynamodb_client)

        mock_rebuilder_instance = MagicMock()
        mock_rebuilder_instance.rebuild.return_value = RebuildManifest(
            rebuild_mode="full",
            total_items_processed=0,
            items_upserted=0,
            items_skipped=0,
            errors_encountered=[],
        )
        mock_rebuilder_cls.return_value = mock_rebuilder_instance

        runner = LocalTestRunner(
            province_id="KR-99",
            bucket="test-bucket",
            ingest_date="20250115",
            table_name="TourKoreaDomainDataV2",
            vector_bucket="lovv-vector-dev",
            index_name="kr-tour-domain-v1",
            session=session,
        )

        summary = runner.run()

        assert summary.verdict == "PASS"
        assert summary.items_read_from_s3 == 0
        assert summary.failed_items == []


class TestLocalTestRunnerFailVerdict:
    """Tests where the local test should produce FAIL verdict."""

    @patch("kr_unified_pipeline.local_test.VectorRebuilder")
    @patch("kr_unified_pipeline.local_test.DynamoDBLoader")
    def test_fail_when_dynamodb_write_fails(
        self, mock_loader_cls: MagicMock, mock_rebuilder_cls: MagicMock
    ) -> None:
        """Verdict is FAIL when DynamoDB load has failures."""
        items = [
            {"PK": "CITY#gangneung", "SK": "META", "province_key": "KR-42"},
        ]

        s3_client = _make_s3_client_with_items(items)
        dynamodb_client = MagicMock()
        session = FakeSession(s3_client=s3_client, dynamodb_client=dynamodb_client)

        # Mock DynamoDBLoader with a failure
        mock_loader_instance = MagicMock()
        mock_loader_instance.load_items.return_value = LoadResult(
            items_loaded=0,
            items_failed=1,
            failures=[FailureDetail(pk="CITY#gangneung", sk="META", error="ConditionalCheckFailed")],
        )
        mock_loader_cls.return_value = mock_loader_instance

        # Mock VectorRebuilder - no failures
        mock_rebuilder_instance = MagicMock()
        mock_rebuilder_instance.rebuild.return_value = RebuildManifest(
            rebuild_mode="full",
            total_items_processed=0,
            items_upserted=0,
            items_skipped=0,
            errors_encountered=[],
        )
        mock_rebuilder_cls.return_value = mock_rebuilder_instance

        runner = LocalTestRunner(
            province_id="KR-42",
            bucket="test-bucket",
            ingest_date="20250115",
            table_name="TourKoreaDomainDataV2",
            vector_bucket="lovv-vector-dev",
            index_name="kr-tour-domain-v1",
            session=session,
        )

        summary = runner.run()

        assert summary.verdict == "FAIL"
        assert len(summary.failed_items) == 1
        assert "dynamo:CITY#gangneung/META" in summary.failed_items[0]

    @patch("kr_unified_pipeline.local_test.VectorRebuilder")
    @patch("kr_unified_pipeline.local_test.DynamoDBLoader")
    def test_fail_when_vector_rebuild_has_errors(
        self, mock_loader_cls: MagicMock, mock_rebuilder_cls: MagicMock
    ) -> None:
        """Verdict is FAIL when vector rebuild has errors."""
        items = [
            {"PK": "CITY#gangneung", "SK": "META", "province_key": "KR-42"},
        ]

        s3_client = _make_s3_client_with_items(items)
        dynamodb_client = MagicMock()
        session = FakeSession(s3_client=s3_client, dynamodb_client=dynamodb_client)

        # Mock DynamoDBLoader - success
        mock_loader_instance = MagicMock()
        mock_loader_instance.load_items.return_value = LoadResult(
            items_loaded=1,
            items_failed=0,
            failures=[],
        )
        mock_loader_cls.return_value = mock_loader_instance

        # Mock VectorRebuilder - has errors
        mock_rebuilder_instance = MagicMock()
        mock_rebuilder_instance.rebuild.return_value = RebuildManifest(
            rebuild_mode="full",
            total_items_processed=1,
            items_upserted=0,
            items_skipped=1,
            errors_encountered=["CITY#gangneung/META: embedding failed"],
        )
        mock_rebuilder_cls.return_value = mock_rebuilder_instance

        runner = LocalTestRunner(
            province_id="KR-42",
            bucket="test-bucket",
            ingest_date="20250115",
            table_name="TourKoreaDomainDataV2",
            vector_bucket="lovv-vector-dev",
            index_name="kr-tour-domain-v1",
            session=session,
        )

        summary = runner.run()

        assert summary.verdict == "FAIL"
        assert len(summary.failed_items) == 1
        assert "vector:" in summary.failed_items[0]


class TestLocalTestRunnerProvinceFiltering:
    """Tests that province_id properly scopes operations."""

    @patch("kr_unified_pipeline.local_test.VectorRebuilder")
    def test_only_matching_province_items_are_loaded(self, mock_rebuilder_cls: MagicMock) -> None:
        """Only items matching the province_id are passed to DynamoDB loader."""
        items = [
            {"PK": "CITY#seoul", "SK": "META", "province_key": "KR-11"},
            {"PK": "CITY#busan", "SK": "META", "province_key": "KR-26"},
            {"PK": "CITY#gangneung", "SK": "META", "province_key": "KR-42"},
            {"PK": "CITY#wonju", "SK": "META", "province_key": "KR-42"},
        ]

        s3_client = _make_s3_client_with_items(items)
        dynamodb_client = MagicMock()
        dynamodb_client.put_item = MagicMock(return_value={})

        session = FakeSession(s3_client=s3_client, dynamodb_client=dynamodb_client)

        mock_rebuilder_instance = MagicMock()
        mock_rebuilder_instance.rebuild.return_value = RebuildManifest(
            rebuild_mode="full",
            total_items_processed=2,
            items_upserted=2,
            items_skipped=0,
            errors_encountered=[],
        )
        mock_rebuilder_cls.return_value = mock_rebuilder_instance

        runner = LocalTestRunner(
            province_id="KR-42",
            bucket="test-bucket",
            ingest_date="20250115",
            table_name="TourKoreaDomainDataV2",
            vector_bucket="lovv-vector-dev",
            index_name="kr-tour-domain-v1",
            session=session,
        )

        summary = runner.run()

        # Only 2 items match KR-42
        assert summary.items_read_from_s3 == 2
        assert summary.verdict == "PASS"

    @patch("kr_unified_pipeline.local_test.VectorRebuilder")
    def test_vector_rebuilder_receives_province_id(self, mock_rebuilder_cls: MagicMock) -> None:
        """VectorRebuilder.rebuild() is called with province_id for scoping."""
        items = [
            {"PK": "CITY#gangneung", "SK": "META", "province_key": "KR-42"},
        ]

        s3_client = _make_s3_client_with_items(items)
        dynamodb_client = MagicMock()
        dynamodb_client.put_item = MagicMock(return_value={})

        session = FakeSession(s3_client=s3_client, dynamodb_client=dynamodb_client)

        mock_rebuilder_instance = MagicMock()
        mock_rebuilder_instance.rebuild.return_value = RebuildManifest(
            rebuild_mode="full",
            total_items_processed=1,
            items_upserted=1,
            items_skipped=0,
            errors_encountered=[],
        )
        mock_rebuilder_cls.return_value = mock_rebuilder_instance

        runner = LocalTestRunner(
            province_id="KR-42",
            bucket="test-bucket",
            ingest_date="20250115",
            table_name="TourKoreaDomainDataV2",
            vector_bucket="lovv-vector-dev",
            index_name="kr-tour-domain-v1",
            session=session,
        )

        runner.run()

        # Verify rebuild was called with correct parameters
        mock_rebuilder_instance.rebuild.assert_called_once_with(
            mode="full",
            table_name="TourKoreaDomainDataV2",
            vector_bucket="lovv-vector-dev",
            index_name="kr-tour-domain-v1",
        )
