from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, assert_never

from boto3.dynamodb.types import TypeSerializer

from kr_details_pipeline.enrichment_engine import EnrichmentResult

_ITEM_SCHEMA_VERSION: Final = "2"
_SERIALIZER = TypeSerializer()


@dataclass(frozen=True, slots=True)
class MissingDynamoKeyError(Exception):
    item_id: str
    missing_key: str

    def __str__(self) -> str:
        return f"Missing DynamoDB key {self.missing_key} for item {self.item_id}"


def update_attraction_enrichment(
    client: Any,
    *,
    table_name: str,
    item: dict[str, Any],
    result: EnrichmentResult,
    item_schema_version: str = _ITEM_SCHEMA_VERSION,
) -> None:
    key = _build_key(item)
    names, values, update_expression = _build_update(result, item_schema_version)
    client.update_item(
        TableName=table_name,
        Key=key,
        UpdateExpression=update_expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="NONE",
    )


def _build_key(item: dict[str, Any]) -> dict[str, Any]:
    pk = item.get("PK")
    sk = item.get("SK")
    item_id = str(item.get("content_id") or item.get("SK") or "unknown")
    if not pk:
        raise MissingDynamoKeyError(item_id=item_id, missing_key="PK")
    if not sk:
        raise MissingDynamoKeyError(item_id=item_id, missing_key="SK")
    return {
        "PK": _serialize_value(pk),
        "SK": _serialize_value(sk),
    }


def _build_update(
    result: EnrichmentResult,
    item_schema_version: str,
) -> tuple[dict[str, str], dict[str, Any], str]:
    match result.status:
        case "succeeded":
            names = {
                "#indoor_outdoor": "indoor_outdoor",
                "#vibe_tags": "vibe_tags",
                "#experience_tags": "experience_tags",
                "#companion_fit": "companion_fit",
                "#schema_version": "schema_version",
                "#metadata_enrichment": "metadata_enrichment",
            }
            values = {
                ":indoor_outdoor": _serialize_value(result.indoor_outdoor),
                ":vibe_tags": _serialize_value(result.vibe_tags),
                ":experience_tags": _serialize_value(result.experience_tags),
                ":companion_fit": _serialize_value(result.companion_fit),
                ":schema_version": _serialize_value(item_schema_version),
                ":metadata_enrichment": _serialize_value(result.metadata_enrichment),
            }
            update_expression = (
                "SET #indoor_outdoor = :indoor_outdoor, "
                "#vibe_tags = :vibe_tags, "
                "#experience_tags = :experience_tags, "
                "#companion_fit = :companion_fit, "
                "#schema_version = :schema_version, "
                "#metadata_enrichment = :metadata_enrichment"
            )
            return names, values, update_expression
        case "failed" | "skipped":
            names = {"#metadata_enrichment": "metadata_enrichment"}
            values = {
                ":metadata_enrichment": _serialize_value(result.metadata_enrichment),
            }
            return names, values, "SET #metadata_enrichment = :metadata_enrichment"
        case unreachable:
            assert_never(unreachable)


def _serialize_value(value: Any) -> dict[str, Any]:
    return _SERIALIZER.serialize(_coerce_value(value))


def _coerce_value(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_coerce_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_value(item) for key, item in value.items()}
    return value
