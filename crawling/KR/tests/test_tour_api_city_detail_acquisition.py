"""Tests for TourAPI city detail collection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from crawling.KR.tour_api_city_detail_acquisition import (
    TourAPIClient,
    TourAPIConfig,
    collect_city_detail,
    fetch_detail,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = {"Content-Type": "application/json"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], int]] = []

    def get(self, url: str, params: dict[str, Any], timeout: int) -> FakeResponse:
        self.calls.append((url, dict(params), timeout))
        endpoint = url.rsplit("/", 1)[-1]
        content_id = params["contentId"]
        if endpoint == "detailCommon2":
            item = {
                "contentid": content_id,
                "title": f"title-{content_id}",
                "tel": "054-000-0000",
                "firstimage": "https://example.test/image.jpg",
            }
        elif endpoint == "detailIntro2":
            item = {
                "contentid": content_id,
                "contenttypeid": params.get("contentTypeId", ""),
                "infocenter": "054-000-0000",
                "usetime": "09:00~18:00",
            }
        else:
            item = {}
        return FakeResponse(
            {
                "response": {
                    "header": {"resultCode": "0000", "resultMsg": "OK"},
                    "body": {"items": {"item": item}},
                }
            }
        )


class TourApiCityDetailAcquisitionTest(unittest.TestCase):
    def test_fetch_detail_calls_common_and_intro_endpoints(self) -> None:
        session = FakeSession()
        client = TourAPIClient(
            TourAPIConfig(service_keys=("dummy-key",), request_delay_seconds=0),
            session=session,
        )

        detail = fetch_detail(client, "126157", "12")

        self.assertEqual("126157", detail["common"]["contentid"])
        self.assertEqual("126157", detail["intro"]["contentid"])
        self.assertEqual(["detailCommon2", "detailIntro2"], [call[0].rsplit("/", 1)[-1] for call in session.calls])
        self.assertEqual("dummy-key", session.calls[0][1]["serviceKey"])

    @patch("crawling.KR.tour_api_city_detail_acquisition.time.sleep")
    def test_collect_city_detail_writes_sample_shaped_city_json(self, mock_sleep: Any) -> None:
        session = FakeSession()
        client = TourAPIClient(
            TourAPIConfig(service_keys=("dummy-key",), request_delay_seconds=0),
            session=session,
        )

        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            root = Path(tmpdir)
            input_path = root / "andong_filtered.json"
            input_path.write_text(
                json.dumps(
                    {
                        "meta": {
                            "province": "경상북도",
                            "city_name_ko": "안동시",
                            "city_name_en": "ANDONG",
                        },
                        "attractions_count_filtered": 1,
                        "festivals_count_filtered": 1,
                        "attractions": [
                            {
                                "contentid": "126157",
                                "contenttypeid": "12",
                                "title": "개목사(안동)",
                                "addr1": "경상북도 안동시",
                                "mapx": "128.6679838568",
                                "mapy": "36.6579094974",
                                "_assigned_theme": "역사·전통",
                            }
                        ],
                        "festivals": [
                            {
                                "contentid": "300001",
                                "contenttypeid": "15",
                                "title": "안동 축제",
                                "addr1": "경상북도 안동시",
                                "mapx": "128.1",
                                "mapy": "36.1",
                                "_assigned_theme": "예술·감성",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_dir = root / "details"
            cache_dir = root / "cache"

            result = collect_city_detail(
                city_list_path=input_path,
                output_dir=output_dir,
                detail_cache_dir=cache_dir,
                client=client,
                overwrite=False,
            )

            output_path = output_dir / "andong.json"
            self.assertTrue(output_path.exists())
            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("ANDONG", saved["meta"]["city_name_en"])
        self.assertEqual(1, saved["attractions_count_filtered"])
        self.assertEqual(1, saved["festivals_count_filtered"])
        self.assertEqual("126157", saved["attractions"][0]["detail"]["common"]["contentid"])
        self.assertEqual("300001", saved["festivals"][0]["detail"]["common"]["contentid"])
        self.assertEqual("collected", saved["attractions"][0]["field_status"]["detail"])
        self.assertEqual(result["meta"]["city_name_ko"], "안동시")
        self.assertEqual(4, len(session.calls))
        mock_sleep.assert_called()


if __name__ == "__main__":
    unittest.main()
