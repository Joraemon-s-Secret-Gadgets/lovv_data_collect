"""GSI query helpers for festival monthly lookup."""

from __future__ import annotations

from typing import Any


def query_festivals_by_month(
    dynamodb_client: Any,
    table_name: str,
    index_name: str,
    month: int,
    *,
    classification_status: str | None = "succeeded",
) -> list[dict[str, Any]]:
    """Query festivals for a given month using the GSI.

    Uses KeyConditionExpression with:
    - entity_type = "festival" (PK)
    - gsi_sk begins_with "FESTIVAL#{month:02d}" (SK prefix)

    Optionally filters by festival_theme_classification.status.

    Args:
        dynamodb_client: boto3 DynamoDB resource or client.
        table_name: DynamoDB table name.
        index_name: GSI name (e.g., "FestivalMonthIndex").
        month: Month number (1-12), or 0 for undated festivals.
        classification_status: Filter by this status. Default "succeeded".
            Set to None to skip filtering.

    Returns:
        List of festival items matching the query.
    """
    month_prefix = f"FESTIVAL#{month:02d}"

    key_condition = "entity_type = :et AND begins_with(gsi_sk, :prefix)"
    expression_values: dict[str, dict[str, str]] = {
        ":et": {"S": "festival"},
        ":prefix": {"S": month_prefix},
    }

    params: dict[str, Any] = {
        "TableName": table_name,
        "IndexName": index_name,
        "KeyConditionExpression": key_condition,
        "ExpressionAttributeValues": expression_values,
    }

    # Add filter expression for classification status if specified
    if classification_status is not None:
        params["FilterExpression"] = "festival_theme_classification.#st = :status"
        params["ExpressionAttributeNames"] = {"#st": "status"}
        params["ExpressionAttributeValues"][":status"] = {"S": classification_status}

    # Handle pagination
    items: list[dict[str, Any]] = []
    while True:
        response = dynamodb_client.query(**params)
        items.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        params["ExclusiveStartKey"] = last_key

    return items
