from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crawling.KR.models import STATUS_MISSING, CityRecord
from crawling.KR.normalizer import build_city_record
from crawling.KR.provinces import MUNICIPALITY_EN_MAP


ROOT_DIR = Path(__file__).resolve().parents[3]


def _page(title: str, extract: str) -> dict[str, Any]:
    return {
        "title": title,
        "extract": extract,
        "coordinates": [{"lat": 37.41, "lon": 127.25}],
        "extlinks": [],
        "langlinks": [],
        "revisions": [],
    }


def _city_from_page(title: str, extract: str, prefecture_id: str) -> CityRecord:
    page = _page(title, extract)
    return build_city_record(
        {
            "source": page,
            "ko": page,
            "ja": {},
            "en": {},
        },
        "2026-06-29T00:00:00+09:00",
        fallback_prefecture_id=prefecture_id,
    )


def test_corrected_gwangju_target_uses_gyeonggi_city_identity() -> None:
    city = _city_from_page("광주시 (경기도)", "광주시는 대한민국 경기도의 시이다.", "KR-41")

    assert city.city_name_ko == "광주시"
    assert city.city_name_en == "GWANGJU-GYEONGGI"
    assert city.city_id == "KR-41-GWANGJU-GYEONGGI"


def test_corrected_yeonggwang_target_uses_jeonnam_city_identity() -> None:
    city = _city_from_page("영광군 (전라남도)", "영광군은 대한민국 전라남도의 군이다.", "KR-46")

    assert city.city_name_ko == "영광군"
    assert city.city_name_en == "YEONGGWANG"
    assert city.city_id == "KR-46-YEONGGWANG"


def test_empty_site_urls_are_marked_missing() -> None:
    city = _city_from_page("영광군 (전라남도)", "영광군은 대한민국 전라남도의 군이다.", "KR-46")

    assert city.site_urls == []
    assert city.field_status["site_urls"] == STATUS_MISSING


def test_corrected_targets_are_aligned_with_municipality_map() -> None:
    gyeonggi_targets = json.loads(
        (ROOT_DIR / "crawling/KR/targets/gyeonggi_municipalities_ko.json").read_text(
            encoding="utf-8",
        ),
    )
    jeonnam_targets = json.loads(
        (ROOT_DIR / "crawling/KR/targets/jeonnam_municipalities_ko.json").read_text(
            encoding="utf-8",
        ),
    )

    assert "광주시 (경기도)" in gyeonggi_targets
    assert "영광군 (전라남도)" in jeonnam_targets
    assert MUNICIPALITY_EN_MAP["광주시 (경기도)"] == "GWANGJU-GYEONGGI"
    assert MUNICIPALITY_EN_MAP["영광군 (전라남도)"] == "YEONGGWANG"
