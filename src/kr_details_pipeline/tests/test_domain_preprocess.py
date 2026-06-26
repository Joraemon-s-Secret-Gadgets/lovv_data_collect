"""Tests for KR domain-specific preprocessing."""

from __future__ import annotations

import json
from pathlib import Path

from kr_details_pipeline import domain_preprocess


def _base_payload() -> dict:
    return {
        "meta": {
            "city_name_en": "Andong",
            "city_name_ko": "안동시",
            "province": "경상북도",
            "lDongRegnCd": "47",
            "lDongSignguCd": "170",
            "sigungus_included": ["안동시"],
            "scraped_at": "2026-06-09T00:00:00Z",
        },
        "attractions": [],
        "festivals": [],
        "visitor_statistics": {
            "year": 2025,
            "annual_totals": {"total_visitors": 1200},
            "annual_daily_averages": {"total_daily_avg": 100},
            "monthly_statistics": [
                {
                    "month": "2025-01",
                    "days": 31,
                    "locals_total": 100,
                    "locals_daily_avg": 3.2,
                    "out_of_town_total": 200,
                    "out_of_town_daily_avg": 6.5,
                    "foreigners_total": 10,
                    "foreigners_daily_avg": 0.3,
                    "total_visitors": 310,
                    "total_daily_avg": 10,
                }
            ],
        },
    }


def test_preprocess_classifies_domains_and_projects_allowed_columns() -> None:
    payload = _base_payload()
    payload["attractions"] = [
        {
            "contentid": "100",
            "contenttypeid": "39",
            "title": "안동식당",
            "mapx": "128.7",
            "mapy": "36.5",
            "detail": {
                "common": {"overview": "restaurant overview", "tel": "054-000-0000"},
                "intro": {
                    "opentimefood": "09:00-18:00",
                    "restdatefood": "Monday",
                    "treatmenu": "간고등어",
                    "parkingfood": "가능",
                    "eventstartdate": "20250101",
                },
            },
        },
        {
            "contentid": "200",
            "contenttypeid": "12",
            "title": "하회마을",
            "mapx": "128.6",
            "mapy": "36.5",
            "_assigned_theme": "history",
            "lclsSystm3": "NA020100",
            "detail": {"intro": {"infocenterculture": "054-111-1111", "usetime": "10:00-17:00"}},
        },
        {
            "contentid": "300",
            "contenttypeid": "25",
            "title": "검수대상",
            "mapx": "128.6",
            "mapy": "36.5",
        },
    ]
    payload["festivals"] = [
        {
            "contentid": "400",
            "title": "안동축제",
            "mapx": "128.7",
            "mapy": "36.4",
            "lclsSystm3": "EV010100",
            "detail": {
                "intro": {
                    "eventstartdate": "20251001",
                    "eventenddate": "20251003",
                    "eventplace": "탈춤공원",
                    "sponsor1": "안동시",
                    "usetimefestival": "무료",
                    "opentimefood": "should not leak",
                }
            },
        }
    ]

    result = domain_preprocess.preprocess_city_payload(payload, source_key="raw/key.json", table_name="TourKoreaDomainData")

    assert result["summary"]["attractions"] == 1
    assert result["summary"]["festivals"] == 1
    assert result["summary"]["visitor_statistics"] == 1
    assert result["summary"]["review"] == 2  # contenttypeid "39" excluded + contenttypeid "25" excluded
    assert result["summary"]["failed"] == 0
    assert result["summary"]["load_items"] == 4  # city_metadata + attraction + festival + visitor_stat

    # contenttypeid "39" is now excluded (no longer "restaurant")
    excluded_items = result["review"]
    excluded_39 = [r for r in excluded_items if r.get("content_id") == "100"]
    assert len(excluded_39) == 1
    assert excluded_39[0]["entity_type"] == "excluded"

    attraction = result["attractions"][0]
    assert attraction["SK"] == "ATTRACTION#200"
    assert attraction["entity_id"] == "ATT-200"
    assert attraction["phone"] == "054-111-1111"
    assert "signature_menu" not in attraction
    # Verify source fields (Req 1.1, 1.3, 1.4)
    assert attraction["lcls_systm3"] == "NA020100"
    assert attraction["source_type"] == "tourapi"
    assert attraction["raw_s3_uri"] == "raw/key.json"
    # Verify deterministic subtype mapping (Req 2.1, 2.2)
    assert attraction["attraction_subtype_code"] == "NA020100"
    assert attraction["attraction_subtype_name"] == "국립공원"
    assert attraction["classification_source"] == "lcls_systm3"
    assert attraction["classification_mapping_version"] == "2026-06-23"

    festival = result["festivals"][0]
    assert festival["SK"] == "FESTIVAL#400"
    assert festival["entity_id"] == "FEST-400"
    assert festival["event_start_date"] == "2025-10-01"
    assert festival["season"] == "autumn"
    assert "opening_hours" not in festival
    # Verify festival source fields (Req 1.2, 1.3, 6.1, 6.2)
    assert festival["lcls_systm3"] == "EV010100"
    assert festival["source_type"] == "tourapi"
    assert festival["raw_s3_uri"] == "raw/key.json"
    assert festival["source_subtype_name"] == "문화관광축제"
    assert festival["source_theme"] == "예술·감성"

    city_item = result["city_metadata"][0]
    assert city_item["province_key"] == "PROVINCE#경상북도"
    assert city_item["city_key"] == "CITY#Andong"

    stat_item = result["visitor_statistics"][0]
    assert stat_item["SK"] == "STAT#202501"
    assert stat_item["domain_sort_key"] == "STAT#202501"


def test_preprocess_routes_missing_required_fields_to_failed() -> None:
    payload = _base_payload()
    payload["attractions"] = [
        {
            "contentid": "500",
            "contenttypeid": "12",
            "mapx": "128.6",
            "mapy": "36.5",
        }
    ]

    result = domain_preprocess.preprocess_city_payload(payload, source_key="raw/key.json", table_name="TourKoreaDomainData")

    assert result["summary"]["failed"] == 1
    assert result["summary"]["attractions"] == 0
    assert result["failed"][0]["quality_status"] == "failed"
    assert "missing_title" in result["failed"][0]["review_queues"]


def test_write_preprocess_output_writes_domain_files(tmp_path: Path) -> None:
    payload = _base_payload()
    payload["attractions"] = [
        {
            "contentid": "100",
            "contenttypeid": "12",
            "title": "하회마을",
            "mapx": "128.7",
            "mapy": "36.5",
            "_assigned_theme": "history",
            "detail": {"intro": {"infocenter": "054-000-0000"}},
        }
    ]
    result = domain_preprocess.preprocess_city_payload(payload, source_key="raw/key.json", table_name="TourKoreaDomainData")

    domain_preprocess.write_preprocess_output(result, tmp_path)

    assert (tmp_path / "normalized" / "attractions.jsonl").exists()
    assert (tmp_path / "load" / "tour_korea_domain_items.jsonl").exists()
    assert (tmp_path / "quality" / "summary.json").exists()
    summary = json.loads((tmp_path / "quality" / "summary.json").read_text(encoding="utf-8"))
    assert summary["attractions"] == 1


# --- GSI SK generation tests (Task 10.1) ---


class TestBuildFestivalGsiSk:
    """Tests for build_festival_gsi_sk() function."""

    def test_valid_date_extracts_month(self) -> None:
        """Standard ISO date extracts the month correctly."""
        result = domain_preprocess.build_festival_gsi_sk("2002", "2026-10-15")
        assert result == "FESTIVAL#10#2002"

    def test_january_month_padded(self) -> None:
        """Single-digit month is zero-padded."""
        result = domain_preprocess.build_festival_gsi_sk("1001", "2026-01-01")
        assert result == "FESTIVAL#01#1001"

    def test_december_month(self) -> None:
        """December (12) is preserved correctly."""
        result = domain_preprocess.build_festival_gsi_sk("3003", "2025-12-25")
        assert result == "FESTIVAL#12#3003"

    def test_missing_date_defaults_to_00(self) -> None:
        """None event_start_date defaults month to 00."""
        result = domain_preprocess.build_festival_gsi_sk("5005", None)
        assert result == "FESTIVAL#00#5005"

    def test_empty_date_defaults_to_00(self) -> None:
        """Empty string event_start_date defaults month to 00."""
        result = domain_preprocess.build_festival_gsi_sk("5005", "")
        assert result == "FESTIVAL#00#5005"

    def test_short_date_defaults_to_00(self) -> None:
        """Date string too short to parse defaults month to 00."""
        result = domain_preprocess.build_festival_gsi_sk("6006", "2026")
        assert result == "FESTIVAL#00#6006"

    def test_multi_month_festival_uses_start_month(self) -> None:
        """Multi-month festival uses start month only (caller provides start date)."""
        # Festival runs Oct-Dec, but we only pass start date
        result = domain_preprocess.build_festival_gsi_sk("7007", "2025-10-01")
        assert result == "FESTIVAL#10#7007"


class TestGsiSkIntegrationInFestivalItem:
    """Tests that gsi_sk is correctly integrated into festival preprocessing."""

    def test_festival_item_has_gsi_sk(self) -> None:
        """Festival items include gsi_sk field after preprocessing."""
        payload = _base_payload()
        payload["festivals"] = [
            {
                "contentid": "400",
                "title": "안동축제",
                "mapx": "128.7",
                "mapy": "36.4",
                "lclsSystm3": "EV010100",
                "detail": {
                    "intro": {
                        "eventstartdate": "20251001",
                        "eventenddate": "20251003",
                        "eventplace": "탈춤공원",
                        "sponsor1": "안동시",
                        "usetimefestival": "무료",
                    }
                },
            }
        ]

        result = domain_preprocess.preprocess_city_payload(
            payload, source_key="raw/key.json", table_name="TourKoreaDomainData"
        )

        festival = result["festivals"][0]
        assert festival["gsi_sk"] == "FESTIVAL#10#400"

    def test_festival_item_gsi_sk_with_missing_start_date(self) -> None:
        """Festival items without event_start_date get gsi_sk with month=00."""
        payload = _base_payload()
        payload["festivals"] = [
            {
                "contentid": "500",
                "title": "날짜미정축제",
                "mapx": "128.7",
                "mapy": "36.4",
                "lclsSystm3": "EV010100",
                "detail": {"intro": {}},
            }
        ]

        result = domain_preprocess.preprocess_city_payload(
            payload, source_key="raw/key.json", table_name="TourKoreaDomainData"
        )

        festival = result["festivals"][0]
        assert festival["gsi_sk"] == "FESTIVAL#00#500"

    def test_festival_gsi_sk_passes_projection(self) -> None:
        """gsi_sk is included in the festival DOMAIN_KEYS so it survives projection."""
        assert "gsi_sk" in domain_preprocess.DOMAIN_KEYS["festival"]
