from __future__ import annotations

from typing import Any

import pytest
from boto3.dynamodb.types import TypeDeserializer

from kr_details_pipeline.enrichment_engine import EnrichmentResult
from kr_details_pipeline.enrichment_persistence import (
    MissingDynamoKeyError,
    update_attraction_enrichment,
)


class FakeDynamoClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


_DESERIALIZER = TypeDeserializer()


def _make_item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "PK": "CITY#GANGNEUNG",
        "SK": "ATTRACTION#12345",
        "entity_type": "attraction",
        "content_id": "12345",
        "title": "테스트 관광지",
        "description": "테스트 설명",
        "theme": "자연·트레킹",
        "theme_tags": ["자연·트레킹"],
        "raw_s3_uri": "s3://example/raw.json",
    }
    base.update(overrides)
    return base


def _deserialize_values(call: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _DESERIALIZER.deserialize(value)
        for key, value in call["ExpressionAttributeValues"].items()
    }


class TestUpdateAttractionEnrichment:
    def test_success_writes_top_level_fields_and_metadata(self) -> None:
        client = FakeDynamoClient()
        item = _make_item()
        result = EnrichmentResult(
            status="succeeded",
            indoor_outdoor="outdoor",
            vibe_tags=["refreshing", "ocean_view"],
            experience_tags=["walking", "photo_spot"],
            companion_fit=["family", "couple"],
            metadata_enrichment={
                "status": "succeeded",
                "model_id": "openai.gpt-oss-120b-1:0",
                "prompt_version": "attraction-metadata-v2",
                "schema_version": "1",
                "generated_at": "2026-06-28T00:00:00Z",
                "input_hash": "sha256:test",
            },
        )

        update_attraction_enrichment(
            client,
            table_name="TourKoreaDomainDataV2",
            item=item,
            result=result,
        )

        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["TableName"] == "TourKoreaDomainDataV2"
        assert _DESERIALIZER.deserialize(call["Key"]["PK"]) == "CITY#GANGNEUNG"
        assert _DESERIALIZER.deserialize(call["Key"]["SK"]) == "ATTRACTION#12345"
        assert call["UpdateExpression"] == (
            "SET #indoor_outdoor = :indoor_outdoor, "
            "#vibe_tags = :vibe_tags, "
            "#experience_tags = :experience_tags, "
            "#companion_fit = :companion_fit, "
            "#schema_version = :schema_version, "
            "#metadata_enrichment = :metadata_enrichment"
        )
        assert set(call["ExpressionAttributeNames"].values()) == {
            "indoor_outdoor",
            "vibe_tags",
            "experience_tags",
            "companion_fit",
            "schema_version",
            "metadata_enrichment",
        }
        values = _deserialize_values(call)
        assert values[":indoor_outdoor"] == "outdoor"
        assert values[":vibe_tags"] == ["refreshing", "ocean_view"]
        assert values[":experience_tags"] == ["walking", "photo_spot"]
        assert values[":companion_fit"] == ["family", "couple"]
        assert values[":schema_version"] == "2"
        assert values[":metadata_enrichment"]["status"] == "succeeded"

    def test_failed_writes_only_metadata_enrichment(self) -> None:
        client = FakeDynamoClient()
        result = EnrichmentResult(
            status="failed",
            metadata_enrichment={
                "status": "failed",
                "error_code": "validation_error",
                "failed_at": "2026-06-28T00:00:00Z",
            },
        )

        update_attraction_enrichment(
            client,
            table_name="TourKoreaDomainDataV2",
            item=_make_item(),
            result=result,
        )

        call = client.calls[0]
        assert call["UpdateExpression"] == "SET #metadata_enrichment = :metadata_enrichment"
        assert call["ExpressionAttributeNames"] == {
            "#metadata_enrichment": "metadata_enrichment"
        }
        values = _deserialize_values(call)
        assert values[":metadata_enrichment"]["status"] == "failed"

    def test_skipped_preserves_existing_top_level_fields(self) -> None:
        client = FakeDynamoClient()
        item = _make_item(
            indoor_outdoor="outdoor",
            vibe_tags=["refreshing"],
            experience_tags=["walking"],
            companion_fit=["family"],
            schema_version="2",
        )
        result = EnrichmentResult(
            status="skipped",
            metadata_enrichment={
                "status": "skipped",
                "model_id": "openai.gpt-oss-120b-1:0",
                "prompt_version": "attraction-metadata-v2",
                "schema_version": "1",
                "generated_at": "2026-06-28T00:00:00Z",
                "input_hash": "sha256:test",
            },
        )

        update_attraction_enrichment(
            client,
            table_name="TourKoreaDomainDataV2",
            item=item,
            result=result,
        )

        call = client.calls[0]
        assert call["UpdateExpression"] == "SET #metadata_enrichment = :metadata_enrichment"
        assert "indoor_outdoor" not in call["ExpressionAttributeNames"].values()
        values = _deserialize_values(call)
        assert values[":metadata_enrichment"]["status"] == "skipped"

    def test_missing_pk_or_sk_raises_without_write(self) -> None:
        client = FakeDynamoClient()
        result = EnrichmentResult(
            status="failed",
            metadata_enrichment={"status": "failed", "error_code": "model_error"},
        )

        with pytest.raises(MissingDynamoKeyError):
            update_attraction_enrichment(
                client,
                table_name="TourKoreaDomainDataV2",
                item=_make_item(SK=""),
                result=result,
            )

        assert client.calls == []
