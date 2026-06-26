from __future__ import annotations

from dataclasses import replace
from typing import Final

from crawling.JP.models import STATUS_COLLECTED, CityRecord, PrefectureRecord
from crawling.JP.prefecture_enrichment import ClimateTable


MANUAL_REQUIRED_CLIMATE_CAPTION: Final[str] = "수작업 필요"


def fill_missing_city_climate_tables(
    cities: list[CityRecord],
    prefectures: list[PrefectureRecord],
) -> list[CityRecord]:
    prefectures_by_id = {prefecture.prefecture_id: prefecture for prefecture in prefectures}
    return [
        _with_prefecture_climate(city, prefectures_by_id.get(city.prefecture_id))
        for city in cities
    ]


def _with_prefecture_climate(
    city: CityRecord,
    prefecture: PrefectureRecord | None,
) -> CityRecord:
    # 도시별 기후를 우선하고, 도도부현 기후는 검토 필요 항목만 채운다.
    if _has_collected_city_climate(city) or not _has_collected_prefecture_climate(prefecture):
        return city
    if prefecture is None or prefecture.climate_table is None:
        return city
    field_status = dict(city.field_status)
    field_status["climate_table"] = STATUS_COLLECTED
    return replace(
        city,
        climate_table=_inherited_climate_table(city, prefecture),
        field_status=field_status,
    )


def _has_collected_city_climate(city: CityRecord) -> bool:
    climate_table = city.climate_table
    if not climate_table:
        return False
    return (
        city.field_status.get("climate_table") == STATUS_COLLECTED
        and climate_table.get("caption") != MANUAL_REQUIRED_CLIMATE_CAPTION
    )


def _has_collected_prefecture_climate(prefecture: PrefectureRecord | None) -> bool:
    if prefecture is None or not prefecture.climate_table:
        return False
    return (
        prefecture.field_status.get("climate_table") == STATUS_COLLECTED
        and prefecture.climate_table.get("caption") != MANUAL_REQUIRED_CLIMATE_CAPTION
    )


def _inherited_climate_table(city: CityRecord, prefecture: PrefectureRecord) -> ClimateTable:
    if prefecture.climate_table is None:
        return {}
    climate_table: ClimateTable = dict(prefecture.climate_table)
    # 하위 검토에서 대체 적용된 기후인지 구분할 수 있게 표시한다.
    climate_table["source_scope"] = "prefecture"
    climate_table["source_prefecture_id"] = prefecture.prefecture_id
    climate_table["source_prefecture_name_ko"] = prefecture.name_ko
    climate_table["source_url"] = prefecture.source_url
    climate_table["inheritance_note"] = (
        f"{city.city_name_ko}의 개별 기후 표가 없어 {prefecture.name_ko} 기후 표를 공통 기준으로 적용했다."
    )
    return climate_table
