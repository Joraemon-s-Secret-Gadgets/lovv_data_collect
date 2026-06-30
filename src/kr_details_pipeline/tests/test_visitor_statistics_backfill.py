from kr_details_pipeline.visitor_statistics_backfill import (
    BackfillInputs,
    build_backfill_plan,
)


def test_build_backfill_plan_creates_missing_rows_from_korean_city_key() -> None:
    inputs = BackfillInputs(
        city_metadata_items=[
            {
                "PK": "CITY#ANDONG",
                "city_id": "KR-47-170",
                "city_name_en": "ANDONG",
                "city_name_ko": "안동시",
                "province": "경상북도",
                "province_key": "PROVINCE#경상북도",
            }
        ],
        existing_statistics_items=[],
        datalab_records={
            "안동시": {
                "year": 2025,
                "annual_totals": {"total_visitors": 1200.0},
                "annual_daily_averages": {"total_visitors": 100.0},
                "monthly_statistics": [
                    {
                        "month": "2025-01",
                        "days": 31,
                        "locals_total": 100.0,
                        "locals_daily_avg": 3.23,
                        "out_of_town_total": 200.0,
                        "out_of_town_daily_avg": 6.45,
                        "foreigners_total": 10.0,
                        "foreigners_daily_avg": 0.32,
                        "total_visitors": 310.0,
                        "total_daily_avg": 10.0,
                    }
                ],
            }
        },
        city_name_lookup={"안동시": "ANDONG"},
        source_key="raw/KR/datalab/20260629/visitor_statistics_2025.json",
    )

    plan = build_backfill_plan(inputs)

    assert plan.summary.planned_item_count == 1
    assert plan.summary.planned_city_count == 1
    assert plan.summary.missing_city_count_after == 0
    assert plan.items[0]["PK"] == "CITY#ANDONG"
    assert plan.items[0]["SK"] == "STAT#202501"
    assert plan.items[0]["domain_sort_key"] == "STAT#202501"
    assert "gsi_sk" not in plan.items[0]


def test_build_backfill_plan_skips_existing_months_for_disambiguated_key() -> None:
    inputs = BackfillInputs(
        city_metadata_items=[
            {
                "PK": "CITY#BUK-BUSAN",
                "city_id": "KR-26-BUK-BUSAN",
                "city_name_en": "BUK-BUSAN",
                "city_name_ko": "북구 (부산광역시)",
                "province": "부산광역시",
                "province_key": "PROVINCE#부산광역시",
            }
        ],
        existing_statistics_items=[
            {
                "PK": "CITY#BUK-BUSAN",
                "SK": "STAT#202501",
            }
        ],
        datalab_records={
            "KR-26-BUK-BUSAN": {
                "city_name_en": "BUK-BUSAN",
                "year": 2025,
                "monthly_statistics": [
                    {"month": "2025-01", "total_visitors": 100.0},
                    {"month": "2025-02", "total_visitors": 200.0},
                ],
            }
        },
        city_name_lookup={},
        source_key="raw/KR/datalab/20260629/visitor_statistics_2025.json",
    )

    plan = build_backfill_plan(inputs)

    assert plan.summary.planned_item_count == 1
    assert plan.items[0]["SK"] == "STAT#202502"
