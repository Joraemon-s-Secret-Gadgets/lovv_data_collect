"""Unit tests for VectorRebuilder."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from kr_unified_pipeline.vector_rebuilder import VectorRebuilder, DEFAULT_GSI_NAME
from kr_vector_index.embed import EmbeddingError


def _make_dynamo_item(pk: str, sk: str, entity_type: str = "city", **kwargs) -> dict:
    """Create a mock DynamoDB item."""
    item = {
        "PK": pk,
        "SK": sk,
        "entity_type": entity_type,
        "city_name_ko": "서울",
        "city_name_en": "Seoul",
        "city_id": "seoul",
        "province": "KR-11",
        "description": "South Korea's capital city",
        "latitude": 37.5665,
        "longitude": 126.9780,
        "quality_status": "passed",
    }
    item.update(kwargs)
    return item


def _make_embedding_response(dim: int = 1024) -> dict:
    """Create a mock Bedrock embedding response."""
    body = json.dumps({"embedding": [0.1] * dim}).encode("utf-8")
    mock_body = MagicMock()
    mock_body.read.return_value = body
    return {"body": mock_body}


class TestVectorRebuilderFullMode:
    """Tests for full rebuild mode."""

    def test_full_rebuild_exports_and_upserts(self):
        """Full rebuild processes all exported items and upserts vectors."""
        dynamo_client = MagicMock()
        bedrock_client = MagicMock()
        s3vectors_client = MagicMock()

        items = [_make_dynamo_item("CITY#seoul", "META#seoul")]

        with patch("kr_unified_pipeline.vector_rebuilder.export_items", return_value=items) as mock_export:
            bedrock_client.invoke_model.return_value = _make_embedding_response()

            rebuilder = VectorRebuilder(dynamo_client, bedrock_client, s3vectors_client)
            manifest = rebuilder.rebuild(
                mode="full",
                table_name="TourKoreaDomainDataV2",
                vector_bucket="lovv-vector-dev",
                index_name="kr-tour-domain-v1",
            )

        # Verify export was called with EntityTypeDomainIndex
        mock_export.assert_called_once_with(
            dynamo_client,
            table_name="TourKoreaDomainDataV2",
            index_name=DEFAULT_GSI_NAME,
        )

        # Verify manifest
        assert manifest.rebuild_mode == "full"
        assert manifest.total_items_processed == 1
        assert manifest.items_upserted == 1
        assert manifest.items_skipped == 0
        assert manifest.start_timestamp != ""
        assert manifest.end_timestamp != ""
        assert manifest.errors_encountered == []

    def test_full_rebuild_empty_export(self):
        """Full rebuild with no items returns empty manifest."""
        dynamo_client = MagicMock()
        bedrock_client = MagicMock()
        s3vectors_client = MagicMock()

        with patch("kr_unified_pipeline.vector_rebuilder.export_items", return_value=[]):
            rebuilder = VectorRebuilder(dynamo_client, bedrock_client, s3vectors_client)
            manifest = rebuilder.rebuild(
                mode="full",
                table_name="TourKoreaDomainDataV2",
                vector_bucket="lovv-vector-dev",
                index_name="kr-tour-domain-v1",
            )

        assert manifest.total_items_processed == 0
        assert manifest.items_upserted == 0
        assert manifest.items_skipped == 0


class TestVectorRebuilderIncrementalMode:
    """Tests for incremental rebuild mode."""

    def test_incremental_filters_by_timestamp(self):
        """Incremental rebuild filters items by last_rebuild_timestamp."""
        dynamo_client = MagicMock()
        bedrock_client = MagicMock()
        s3vectors_client = MagicMock()

        old_item = _make_dynamo_item("CITY#busan", "META#busan", updated_at="2024-01-01T00:00:00Z")
        new_item = _make_dynamo_item("CITY#seoul", "META#seoul", updated_at="2024-06-15T12:00:00Z")
        items = [old_item, new_item]

        with patch("kr_unified_pipeline.vector_rebuilder.export_items", return_value=items):
            bedrock_client.invoke_model.return_value = _make_embedding_response()

            rebuilder = VectorRebuilder(dynamo_client, bedrock_client, s3vectors_client)
            manifest = rebuilder.rebuild(
                mode="incremental",
                table_name="TourKoreaDomainDataV2",
                vector_bucket="lovv-vector-dev",
                index_name="kr-tour-domain-v1",
                last_rebuild_timestamp="2024-03-01T00:00:00Z",
            )

        # Only the new item should be processed
        assert manifest.total_items_processed == 1
        assert manifest.items_upserted == 1

    def test_incremental_includes_items_without_timestamp(self):
        """Incremental mode includes items with no timestamp field."""
        dynamo_client = MagicMock()
        bedrock_client = MagicMock()
        s3vectors_client = MagicMock()

        no_ts_item = _make_dynamo_item("CITY#daegu", "META#daegu")
        items = [no_ts_item]

        with patch("kr_unified_pipeline.vector_rebuilder.export_items", return_value=items):
            bedrock_client.invoke_model.return_value = _make_embedding_response()

            rebuilder = VectorRebuilder(dynamo_client, bedrock_client, s3vectors_client)
            manifest = rebuilder.rebuild(
                mode="incremental",
                table_name="TourKoreaDomainDataV2",
                vector_bucket="lovv-vector-dev",
                index_name="kr-tour-domain-v1",
                last_rebuild_timestamp="2024-03-01T00:00:00Z",
            )

        # Item with no timestamp should still be included
        assert manifest.total_items_processed == 1
        assert manifest.items_upserted == 1


class TestVectorRebuilderErrorHandling:
    """Tests for error handling (skip failed items)."""

    def test_skips_failed_embedding_items(self):
        """When embedding fails for an item, it is skipped and processing continues."""
        dynamo_client = MagicMock()
        bedrock_client = MagicMock()
        s3vectors_client = MagicMock()

        items = [
            _make_dynamo_item("CITY#seoul", "META#seoul"),
            _make_dynamo_item("CITY#busan", "META#busan"),
        ]

        embed_call_count = [0]

        def mock_embed_chunks(client, chunks):
            embed_call_count[0] += 1
            if embed_call_count[0] == 1:
                raise EmbeddingError("Bedrock throttle error")
            return [[0.1] * 1024]

        with patch("kr_unified_pipeline.vector_rebuilder.export_items", return_value=items), \
             patch("kr_unified_pipeline.vector_rebuilder.embed_chunks", side_effect=mock_embed_chunks):

            rebuilder = VectorRebuilder(dynamo_client, bedrock_client, s3vectors_client)
            manifest = rebuilder.rebuild(
                mode="full",
                table_name="TourKoreaDomainDataV2",
                vector_bucket="lovv-vector-dev",
                index_name="kr-tour-domain-v1",
            )

        assert manifest.total_items_processed == 2
        assert manifest.items_skipped == 1
        assert manifest.items_upserted == 1
        assert len(manifest.errors_encountered) == 1
        assert "CITY#seoul" in manifest.errors_encountered[0]

    def test_logs_pk_sk_on_embedding_failure(self):
        """Failed embedding error message includes PK and SK."""
        dynamo_client = MagicMock()
        bedrock_client = MagicMock()
        s3vectors_client = MagicMock()

        items = [_make_dynamo_item("CITY#seoul", "META#seoul")]

        with patch("kr_unified_pipeline.vector_rebuilder.export_items", return_value=items):
            bedrock_client.invoke_model.side_effect = RuntimeError("timeout")

            rebuilder = VectorRebuilder(dynamo_client, bedrock_client, s3vectors_client)
            manifest = rebuilder.rebuild(
                mode="full",
                table_name="TourKoreaDomainDataV2",
                vector_bucket="lovv-vector-dev",
                index_name="kr-tour-domain-v1",
            )

        assert manifest.items_skipped == 1
        assert "PK=CITY#seoul" in manifest.errors_encountered[0]
        assert "SK=META#seoul" in manifest.errors_encountered[0]


class TestVectorRebuilderManifest:
    """Tests for rebuild manifest recording."""

    def test_manifest_has_all_required_fields(self):
        """Manifest includes all required fields per Requirement 12.5."""
        dynamo_client = MagicMock()
        bedrock_client = MagicMock()
        s3vectors_client = MagicMock()

        items = [_make_dynamo_item("CITY#seoul", "META#seoul")]

        with patch("kr_unified_pipeline.vector_rebuilder.export_items", return_value=items):
            bedrock_client.invoke_model.return_value = _make_embedding_response()

            rebuilder = VectorRebuilder(dynamo_client, bedrock_client, s3vectors_client)
            manifest = rebuilder.rebuild(
                mode="full",
                table_name="TourKoreaDomainDataV2",
                vector_bucket="lovv-vector-dev",
                index_name="kr-tour-domain-v1",
            )

        # All RebuildManifest fields must be populated
        assert manifest.rebuild_mode == "full"
        assert manifest.start_timestamp != ""
        assert manifest.end_timestamp != ""
        assert manifest.total_items_processed == 1
        assert manifest.items_upserted == 1
        assert manifest.items_skipped == 0
        assert isinstance(manifest.errors_encountered, list)
