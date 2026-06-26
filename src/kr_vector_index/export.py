"""Export vectorizable KR domain items from DynamoDB."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from boto3.dynamodb.types import TypeDeserializer

VECTORIZABLE_ENTITY_TYPES = ("city", "city_metadata", "attraction", "festival")


def should_vectorize(item: dict[str, Any]) -> bool:
    entity_type = str(item.get("entity_type") or "")
    if entity_type == "visitor_statistics":
        return False
    if entity_type not in VECTORIZABLE_ENTITY_TYPES:
        return False
    quality_status = str(item.get("quality_status") or "passed")
    return quality_status == "passed"


def iter_gsi3_items(
    client: Any,
    *,
    table_name: str,
    entity_type: str,
    index_name: str = "GSI3",
) -> Iterator[dict[str, Any]]:
    """Query a GSI by entity type and yield deserialized DynamoDB items.

    Args:
        client: boto3 DynamoDB client.
        table_name: Name of the DynamoDB table.
        entity_type: The entity type to query (e.g. "city", "attraction").
        index_name: Name of the GSI to query. Defaults to "GSI3" for backward
            compatibility with the existing TourKoreaDomainData table. Pass
            "EntityTypeDomainIndex" when querying the new V2 table.
    """

    deserializer = TypeDeserializer()
    exclusive_start_key: dict[str, Any] | None = None
    while True:
        params: dict[str, Any] = {
            "TableName": table_name,
            "IndexName": index_name,
            "KeyConditionExpression": "entity_type = :entity_type",
            "ExpressionAttributeValues": {
                ":entity_type": {"S": entity_type},
            },
        }
        if exclusive_start_key:
            params["ExclusiveStartKey"] = exclusive_start_key
        response = client.query(**params)
        for raw_item in response.get("Items", []):
            item = {key: deserializer.deserialize(value) for key, value in raw_item.items()}
            if should_vectorize(item):
                yield item
        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break


def export_items(
    client: Any,
    *,
    table_name: str,
    entity_types: tuple[str, ...] = VECTORIZABLE_ENTITY_TYPES,
    city_pk: str | None = None,
    index_name: str = "GSI3",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entity_type in entity_types:
        for item in iter_gsi3_items(client, table_name=table_name, entity_type=entity_type, index_name=index_name):
            if city_pk and item.get("PK") != city_pk:
                continue
            items.append(item)
    return items


def count_by_entity_type(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        entity_type = str(item.get("entity_type") or "unknown")
        counts[entity_type] = counts.get(entity_type, 0) + 1
    return counts
