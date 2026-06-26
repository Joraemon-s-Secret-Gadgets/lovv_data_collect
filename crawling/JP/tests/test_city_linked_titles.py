from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Final

from crawling.JP.pipeline import PageTarget, acquire_city_data


type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

HACHIOJI_KO_TITLE: Final[str] = "하치오지시"
TOKYO_KO_TITLE: Final[str] = "도쿄도"


class LinkedTitleOnlyClient:
    def __init__(self) -> None:
        self._payloads: dict[str, dict[str, JsonValue]] = {
            HACHIOJI_KO_TITLE: {
                "query": {
                    "pages": [
                        {
                            "title": HACHIOJI_KO_TITLE,
                            "extract": "하치오지시는 일본 도쿄도 서부에 위치한 도시이다.",
                            "coordinates": [{"lat": 35.6664, "lon": 139.3160}],
                            "extlinks": [],
                            "langlinks": [
                                {"lang": "ja", "title": "八王子市"},
                                {"lang": "en", "title": "Hachioji"},
                            ],
                        },
                    ],
                },
            },
            TOKYO_KO_TITLE: {
                "query": {
                    "pages": [
                        {
                            "title": TOKYO_KO_TITLE,
                            "extract": "도쿄도는 일본의 광역자치단체이다.",
                            "coordinates": [{"lat": 35.6895, "lon": 139.6917}],
                            "extlinks": [],
                            "langlinks": [],
                        },
                    ],
                },
            },
        }

    def fetch_page(self, lang: str, title: str) -> dict[str, JsonValue]:
        if lang != "ko" or title not in self._payloads:
            raise AssertionError("Linked title stubs should not require fetching linked pages.")
        return self._payloads[title]


class CityLinkedTitleTest(unittest.TestCase):
    def test_korean_source_keeps_linked_title_stubs_when_coordinates_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _, cities = acquire_city_data(
                titles=[PageTarget(title=HACHIOJI_KO_TITLE, lang="ko", prefecture_id="JP-13")],
                output_dir=Path(tmpdir),
                client=LinkedTitleOnlyClient(),
            )

        self.assertEqual("八王子市", cities[0].city_name_ja)
        self.assertEqual("Hachioji", cities[0].city_name_en)
