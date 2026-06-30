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
        province = city_record.get("province") or ""
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
                "province": province,
                "lDongRegnCd": city_record.get("lDongRegnCd"),
                "lDongSignguCd": city_record.get("lDongSignguCd"),
                "source_status": payload.get("status", ""),
                # GSI key fields
                "city_key": city_pk,
                "province_key": province,
                "domain_sort_key": f"city#{city_record.get('city_id', '')}",
                "gsi_sk": f"city#{city_record.get('city_id', '')}",
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
                _normalize_item(item, city_pk=city_pk, province=city_record.get("province")),
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


def _normalize_item(item: dict[str, Any], *, city_pk: str, province: Any = None) -> dict[str, Any]:
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

    # GSI key fields for TourKoreaDomainDataV2
    # city_key: same as PK for CityDomainIndex GSI
    result["city_key"] = city_pk
    # province_key: extracted from item or inferred from city_pk
    result["province_key"] = item.get("province_key") or item.get("province") or province or ""
    # domain_sort_key: entity_type#content_id for ordering within GSI
    result["domain_sort_key"] = f"{entity_type}#{content_id}" if content_id else f"{entity_type}#{entity_id}"
    # gsi_sk: for FestivalMonthIndex — FESTIVAL#{month:02d}#{content_id}
    if entity_type == "festival":
        month = item.get("month") or item.get("eventstartdate", "")[:2] or "00"
        result["gsi_sk"] = f"FESTIVAL#{month}#{content_id}"
    else:
        result["gsi_sk"] = f"{entity_type}#{content_id}"

    # Preserve image_status field when present (e.g. "needs_review" from image processing)
    if item.get("image_status"):
        result["image_status"] = item["image_status"]

    return _normalize_visitor_statistics_keys(result)


def _write_item(client: DynamoClient, table_name: str, item: dict[str, Any]) -> None:
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    item = _normalize_visitor_statistics_keys(item)
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


def _normalize_visitor_statistics_keys(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("entity_type") != "visitor_statistics":
        return item

    result = dict(item)
    month = str(result.get("month") or "UNKNOWN")
    sk = str(result.get("SK") or f"STAT#{month}")
    result["SK"] = sk
    result["domain_sort_key"] = sk

    province_key = str(result.get("province_key") or "")
    province = str(result.get("province") or "")
    if province_key.startswith("PROVINCE#"):
        result["province_key"] = province_key
    elif province_key and province_key != "UNKNOWN":
        result["province_key"] = f"PROVINCE#{province_key}"
    elif province:
        result["province_key"] = province if province.startswith("PROVINCE#") else f"PROVINCE#{province}"
    else:
        result["province_key"] = "PROVINCE#UNKNOWN"

    result.pop("gsi_sk", None)
    return result
