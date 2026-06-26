"""Load helpers to persist transformed KR pipeline outputs into DynamoDB."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol


class DynamoClient(Protocol):
    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        ...


class LoadResult:
    passed: int
    failed: int

    def __init__(self, passed: int, failed: int) -> None:
        self.passed = passed
        self.failed = failed


def load_processed_city(payload: dict[str, Any], table_name: str, client: DynamoClient) -> LoadResult:
    city_record = payload.get("city_record")
    records = payload.get("records") if isinstance(payload.get("records"), list) else []

    passed = 0
    failed = 0

    if not isinstance(city_record, dict):
        raise ValueError("processed city payload must include city_record")

    city_pk = _city_pk(city_record.get("city_name_en"))

    if city_record.get("city_id"):
        _write_item(
            client,
            table_name,
            {
                "PK": city_pk,
                "SK": "METADATA#city",
                "entity_type": "city",
                "city_id": city_record.get("city_id"),
                "city_name_en": city_record.get("city_name_en"),
                "city_name_ko": city_record.get("city_name_ko"),
                "province": city_record.get("province"),
                "lDongRegnCd": city_record.get("lDongRegnCd"),
                "lDongSignguCd": city_record.get("lDongSignguCd"),
                "source_status": payload.get("status", ""),
            },
        )
        passed += 1

    for item in records:
        if not isinstance(item, dict):
            failed += 1
            continue
        try:
            _write_item(
                client,
                table_name,
                _normalize_item(item, city_pk=city_pk),
            )
            passed += 1
        except Exception as exc:
            city_name = city_record.get("city_name_en", "UNKNOWN")
            content_id = item.get("content_id") if isinstance(item, dict) else None
            print(
                f"[ERROR] put failed city={city_name} entity={item.get('entity_id') if isinstance(item, dict) else '<invalid>'} "
                f"content_id={content_id} error={type(exc).__name__}: {exc}"
            )
            failed += 1

    return LoadResult(passed, failed)


def load_processed_payload(payload: dict[str, Any], table_name: str, client: DynamoClient) -> LoadResult:
    return load_processed_city(payload, table_name, client)


def _normalize_item(item: dict[str, Any], *, city_pk: str) -> dict[str, Any]:
    entity_type = item.get("entity_type", "")
    entity_id = item.get("entity_id", "")
    content_id = item.get("content_id", "")
    if not entity_type:
        raise ValueError("entity_type is required")

    sk = item.get("SK")
    if not sk:
        if entity_type == "visitor_statistics":
            month = item.get("month") or "UNKNOWN"
            sk = f"STAT#{month}"
        elif entity_id.startswith("FEST-"):
            sk = f"FESTIVAL#{content_id}"
        else:
            sk = f"ATTRACTION#{content_id}"

    result = {
        "PK": city_pk,
        "SK": str(sk),
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "content_id": str(content_id),
        "quality_status": item.get("quality_status", ""),
        "source": item.get("source_key", ""),
        "title": item.get("title", ""),
        "theme": item.get("theme", ""),
        "description": item.get("description", ""),
        "theme_tags": item.get("theme_tags", []),
        "season_tags": item.get("season_tags", []),
        "visit_months": item.get("visit_months", []),
        "longitude": item.get("longitude"),
        "latitude": item.get("latitude"),
        "geohash_prefix": item.get("geohash_prefix") or "UNKNOWN",
        "address": item.get("address", ""),
        "phone": item.get("phone", ""),
        "image_url": item.get("image_url", ""),
        "eventstartdate": item.get("eventstartdate"),
        "eventenddate": item.get("eventenddate"),
        "month": item.get("month"),
        "season": item.get("season"),
        "statistics": item.get("statistics"),
        "item_count": 1,
    }

    # Preserve image_status field when present (e.g. "needs_review" from image processing)
    if item.get("image_status"):
        result["image_status"] = item["image_status"]

    return result


def _write_item(client: DynamoClient, table_name: str, item: dict[str, Any]) -> None:
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    serialized = {key: serializer.serialize(_coerce_value(value)) for key, value in item.items()}
    client.put_item(TableName=table_name, Item=serialized)


def _city_pk(city_name_en: Any) -> str:
    return f"CITY#{str(city_name_en or 'UNKNOWN')}"


def _coerce_value(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_coerce_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_value(item) for key, item in value.items()}
    return value
