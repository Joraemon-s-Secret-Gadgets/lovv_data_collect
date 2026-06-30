from __future__ import annotations

from typing import Any, Final

EXPECTED_VISITOR_STATISTICS_ROWS: Final = 2820
ENRICHMENT_FIELDS: Final = (
    "metadata_enrichment",
    "indoor_outdoor",
    "vibe_tags",
    "experience_tags",
    "companion_fit",
    "schema_version",
)


def build_preflight_summary(
    client: Any,
    *,
    table_name: str,
    entity_index_name: str,
) -> dict[str, Any]:
    visitor_count = _count_entity(
        client,
        table_name=table_name,
        index_name=entity_index_name,
        entity_type="visitor_statistics",
    )
    visitor_gsi_count = _count_entity_filter(
        client,
        table_name=table_name,
        entity_type="visitor_statistics",
        filter_expression="entity_type = :entity_type AND attribute_exists(gsi_sk)",
        extra_values={},
    )
    visitor_bad_sk_count = _count_entity_filter(
        client,
        table_name=table_name,
        entity_type="visitor_statistics",
        filter_expression="entity_type = :entity_type AND NOT begins_with(SK, :prefix)",
        extra_values={":prefix": {"S": "STAT#"}},
    )
    visitor_missing_domain_sort_key_count = _count_entity_filter(
        client,
        table_name=table_name,
        entity_type="visitor_statistics",
        filter_expression="entity_type = :entity_type AND attribute_not_exists(domain_sort_key)",
        extra_values={},
    )
    visitor_bad_domain_sort_key_count = _count_entity_filter(
        client,
        table_name=table_name,
        entity_type="visitor_statistics",
        filter_expression="entity_type = :entity_type AND NOT begins_with(domain_sort_key, :prefix)",
        extra_values={":prefix": {"S": "STAT#"}},
    )
    attraction_count = _count_entity(
        client,
        table_name=table_name,
        index_name=entity_index_name,
        entity_type="attraction",
    )
    enrichment_counts = {
        field: _count_entity_attribute(
            client,
            table_name=table_name,
            entity_type="attraction",
            attribute_name=field,
        )
        for field in ENRICHMENT_FIELDS
    }
    enriched_rows = enrichment_counts["metadata_enrichment"]
    return {
        "visitor_statistics": {
            "expected_rows": EXPECTED_VISITOR_STATISTICS_ROWS,
            "row_count": visitor_count,
            "gsi_sk_count": visitor_gsi_count,
            "non_stat_sk_count": visitor_bad_sk_count,
            "missing_domain_sort_key_count": visitor_missing_domain_sort_key_count,
            "non_stat_domain_sort_key_count": visitor_bad_domain_sort_key_count,
            "coverage_ok": (
                visitor_count == EXPECTED_VISITOR_STATISTICS_ROWS
                and visitor_gsi_count == 0
                and visitor_bad_sk_count == 0
                and visitor_missing_domain_sort_key_count == 0
                and visitor_bad_domain_sort_key_count == 0
            ),
        },
        "enrichment": {
            "attraction_count": attraction_count,
            "mode": "enrichment-complete" if enriched_rows > 0 else "non-enrichment-complete",
            **enrichment_counts,
        },
    }


def _count_entity(
    client: Any,
    *,
    table_name: str,
    index_name: str,
    entity_type: str,
) -> int:
    total = 0
    exclusive_start_key: dict[str, Any] | None = None
    while True:
        params: dict[str, Any] = {
            "TableName": table_name,
            "IndexName": index_name,
            "KeyConditionExpression": "entity_type = :entity_type",
            "ExpressionAttributeValues": {
                ":entity_type": {"S": entity_type},
            },
            "Select": "COUNT",
        }
        if exclusive_start_key:
            params["ExclusiveStartKey"] = exclusive_start_key
        response = client.query(**params)
        total += int(response.get("Count", 0) or 0)
        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key:
            return total


def _count_entity_attribute(
    client: Any,
    *,
    table_name: str,
    entity_type: str,
    attribute_name: str,
) -> int:
    return _count_entity_filter(
        client,
        table_name=table_name,
        entity_type=entity_type,
        filter_expression="entity_type = :entity_type AND attribute_exists(#target_attribute)",
        extra_values={},
        expression_names={"#target_attribute": attribute_name},
    )


def _count_entity_filter(
    client: Any,
    *,
    table_name: str,
    entity_type: str,
    filter_expression: str,
    extra_values: dict[str, dict[str, str]],
    expression_names: dict[str, str] | None = None,
) -> int:
    total = 0
    exclusive_start_key: dict[str, Any] | None = None
    while True:
        params: dict[str, Any] = {
            "TableName": table_name,
            "FilterExpression": filter_expression,
            "ExpressionAttributeValues": {
                ":entity_type": {"S": entity_type},
                **extra_values,
            },
            "Select": "COUNT",
        }
        if expression_names:
            params["ExpressionAttributeNames"] = expression_names
        if exclusive_start_key:
            params["ExclusiveStartKey"] = exclusive_start_key
        response = client.scan(**params)
        total += int(response.get("Count", 0) or 0)
        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key:
            return total
