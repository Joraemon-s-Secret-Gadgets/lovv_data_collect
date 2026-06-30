from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class BackfillInputs:
    city_metadata_items: Sequence[Mapping[str, Any]]
    existing_statistics_items: Sequence[Mapping[str, Any]]
    datalab_records: Mapping[str, Mapping[str, Any]]
    city_name_lookup: Mapping[str, str]
    source_key: str


@dataclass(frozen=True, slots=True)
class BackfillSummary:
    city_metadata_count: int
    existing_statistics_count: int
    existing_statistics_city_count: int
    datalab_source_count: int
    matched_source_count: int
    unmatched_source_count: int
    source_without_city_count: int
    planned_item_count: int
    planned_city_count: int
    missing_city_count_before: int
    missing_city_count_after: int
    sample_missing_city_pks_after: tuple[str, ...]
    sample_unmatched_source_keys: tuple[str, ...]
    sample_source_keys_without_city: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    items: tuple[dict[str, Any], ...]
    summary: BackfillSummary


def build_backfill_plan(inputs: BackfillInputs) -> BackfillPlan:
    city_by_pk = {_string(item.get("PK")): item for item in inputs.city_metadata_items}
    city_by_pk.pop("", None)
    existing_months = _existing_months_by_city(inputs.existing_statistics_items)
    planned_items: list[dict[str, Any]] = []
    planned_city_pks: set[str] = set()
    matched_source_count = 0
    unmatched_source_keys: list[str] = []
    source_keys_without_city: list[str] = []

    for source_key, stat_record in inputs.datalab_records.items():
        city_pk = _resolve_city_pk(source_key, stat_record, inputs.city_name_lookup)
        if not city_pk:
            unmatched_source_keys.append(source_key)
            continue
        city_item = city_by_pk.get(city_pk)
        if city_item is None:
            source_keys_without_city.append(source_key)
            continue
        matched_source_count += 1
        existing_for_city = existing_months.get(city_pk, set())
        for item in _build_items_for_city(city_item, stat_record, inputs.source_key):
            sk = _string(item.get("SK"))
            if sk in existing_for_city:
                continue
            planned_items.append(item)
            planned_city_pks.add(city_pk)

    city_pks = set(city_by_pk)
    existing_city_pks = set(existing_months)
    missing_before = city_pks - existing_city_pks
    missing_after = missing_before - planned_city_pks
    return BackfillPlan(
        items=tuple(planned_items),
        summary=BackfillSummary(
            city_metadata_count=len(city_pks),
            existing_statistics_count=len(inputs.existing_statistics_items),
            existing_statistics_city_count=len(existing_city_pks),
            datalab_source_count=len(inputs.datalab_records),
            matched_source_count=matched_source_count,
            unmatched_source_count=len(unmatched_source_keys),
            source_without_city_count=len(source_keys_without_city),
            planned_item_count=len(planned_items),
            planned_city_count=len(planned_city_pks),
            missing_city_count_before=len(missing_before),
            missing_city_count_after=len(missing_after),
            sample_missing_city_pks_after=tuple(sorted(missing_after)[:20]),
            sample_unmatched_source_keys=tuple(unmatched_source_keys[:20]),
            sample_source_keys_without_city=tuple(source_keys_without_city[:20]),
        ),
    )


def _existing_months_by_city(
    existing_statistics_items: Sequence[Mapping[str, Any]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for item in existing_statistics_items:
        pk = _string(item.get("PK"))
        sk = _string(item.get("SK"))
        if not pk or not sk:
            continue
        result.setdefault(pk, set()).add(sk)
    return result


def _resolve_city_pk(
    source_key: str,
    stat_record: Mapping[str, Any],
    city_name_lookup: Mapping[str, str],
) -> str | None:
    city_name_en = (
        _string(stat_record.get("city_name_en"))
        if source_key.startswith("KR-")
        else city_name_lookup.get(source_key, "")
    )
    normalized = _string(city_name_en).replace("_", "-").upper()
    if not normalized:
        return None
    return f"CITY#{normalized}"


def _build_items_for_city(
    city_item: Mapping[str, Any],
    stat_record: Mapping[str, Any],
    source_key: str,
) -> tuple[dict[str, Any], ...]:
    rows = stat_record.get("monthly_statistics")
    if not isinstance(rows, list):
        return ()

    city_pk = _string(city_item.get("PK"))
    city_name_en = _string(city_item.get("city_name_en"))
    city_id = _string(city_item.get("city_id"))
    city_name_ko = _string(city_item.get("city_name_ko"))
    province = _string(city_item.get("province"))
    province_key = (
        _string(city_item.get("province_key")) or f"PROVINCE#{province or 'UNKNOWN'}"
    )
    annual_totals = (
        stat_record.get("annual_totals")
        if isinstance(stat_record.get("annual_totals"), dict)
        else {}
    )
    annual_daily_averages = (
        stat_record.get("annual_daily_averages")
        if isinstance(stat_record.get("annual_daily_averages"), dict)
        else {}
    )
    year = _int_or_none(stat_record.get("year"))
    items: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        month = _normalize_month(_string(row.get("month")))
        if month is None:
            continue
        items.append(
            {
                "PK": city_pk,
                "SK": f"STAT#{month}",
                "entity_id": f"STAT-{city_id}-{month}",
                "entity_type": "visitor_statistics",
                "city_id": city_id,
                "city_name_en": city_name_en,
                "city_name_ko": city_name_ko,
                "province": province,
                "province_key": province_key,
                "city_key": city_pk,
                "domain_sort_key": f"STAT#{month}",
                "year": year,
                "month": month,
                "days": row.get("days"),
                "locals_total": row.get("locals_total"),
                "locals_daily_avg": row.get("locals_daily_avg"),
                "out_of_town_total": row.get("out_of_town_total"),
                "out_of_town_daily_avg": row.get("out_of_town_daily_avg"),
                "foreigners_total": row.get("foreigners_total"),
                "foreigners_daily_avg": row.get("foreigners_daily_avg"),
                "total_visitors": row.get("total_visitors"),
                "total_daily_avg": row.get("total_daily_avg"),
                "annual_totals": annual_totals,
                "annual_daily_averages": annual_daily_averages,
                "quality_status": "passed",
                "review_queues": [],
                "source_key": source_key,
            }
        )
    return tuple(items)


def _normalize_month(value: str) -> str | None:
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) != 6:
        return None
    return digits


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _string(value: Any) -> str:
    return str(value or "").strip()
