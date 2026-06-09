"""Tests for regional TourAPI city-detail orchestration."""

from __future__ import annotations

import unittest
from typing import Any

from crawling.KR.tour_api_region_detail_acquisition import (
    _filter_records,
    collect_city_list,
    fetch_all_items,
)


class FakeClient:
    def request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if endpoint == "areaBasedList2":
            items = [
                {
                    "contentid": "a1",
                    "contenttypeid": "12",
                    "title": "관광지",
                    "lclsSystm3": "HS010100",
                }
            ]
        else:
            items = [
                {
                    "contentid": "f1",
                    "contenttypeid": "15",
                    "title": "축제",
                    "lclsSystm3": "EV010100",
                }
            ]
        return {
            "response": {
                "body": {
                    "items": {"item": items},
                    "totalCount": len(items),
                }
            }
        }


class TourApiRegionDetailAcquisitionTest(unittest.TestCase):
    def test_fetch_all_items_reads_items_from_response(self) -> None:
        items = fetch_all_items(FakeClient(), "areaBasedList2", {"lDongRegnCd": "47"})
        self.assertEqual(1, len(items))
        self.assertEqual("a1", items[0]["contentid"])

    def test_filter_records_assigns_theme_by_lcls_code(self) -> None:
        records = [{"contentid": "a1", "lclsSystm3": "HS010100"}]
        filtered = _filter_records(records, {"HS010100": "역사·전통"}, set())
        self.assertEqual(1, len(filtered))
        self.assertEqual("역사·전통", filtered[0]["_assigned_theme"])

    def test_collect_city_list_builds_sample_input_shape(self) -> None:
        payload = collect_city_list(
            client=FakeClient(),
            target={
                "lDongRegnCd": "47",
                "lDongRegnNm": "경상북도",
                "lDongSignguCd": "170",
                "lDongSignguNm": "안동시",
            },
            city_name_en="ANDONG",
            attraction_theme_map={"HS010100": "역사·전통"},
            festival_theme_map={"EV010100": "예술·감성"},
        )

        self.assertEqual("ANDONG", payload["meta"]["city_name_en"])
        self.assertEqual(1, payload["attractions_count_filtered"])
        self.assertEqual(1, payload["festivals_count_filtered"])
        self.assertEqual("a1", payload["attractions"][0]["contentid"])
        self.assertEqual("f1", payload["festivals"][0]["contentid"])


if __name__ == "__main__":
    unittest.main()
