from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Final

from crawling.JP.pipeline import PageTarget, acquire_city_data
from crawling.JP.wikipedia_client import parse_wikipedia_html


type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

CHIYODA_KO_TITLE: Final[str] = "지요다구"
TOKYO_KO_TITLE: Final[str] = "도쿄도"


class TokyoPrefectureClient:
    def __init__(self) -> None:
        self._pages: dict[tuple[str, str], dict[str, JsonValue]] = {
            ("ko", CHIYODA_KO_TITLE): {
                "title": CHIYODA_KO_TITLE,
                "extract": "지요다구는 일본 도쿄도의 특별구이다.",
                "coordinates": [{"lat": 35.694, "lon": 139.7536}],
                "extlinks": [{"url": "https://www.city.chiyoda.lg.jp/"}],
                "langlinks": [
                    {"lang": "ja", "title": "千代田区"},
                    {"lang": "en", "title": "Chiyoda, Tokyo"},
                ],
            },
            ("ko", TOKYO_KO_TITLE): {
                "title": TOKYO_KO_TITLE,
                "extract": "도쿄도는 일본의 수도권에 있는 광역자치단체이다.",
                "coordinates": [{"lat": 35.6895, "lon": 139.6917}],
                "extlinks": [{"url": "https://www.metro.tokyo.lg.jp/"}],
                "langlinks": [
                    {"lang": "ja", "title": "東京都"},
                    {"lang": "en", "title": "Tokyo"},
                ],
                "revisions": [
                    {
                        "slots": {
                            "main": {
                                "content": (
                                    "'''도쿄도'''는 일본의 광역자치단체이다.\n\n"
                                    "== 지리 ==\n도쿄도는 간토 지방 남부에 위치하며 도쿄만과 도서 지역을 포함한다.\n\n"
                                    "== 기후 ==\n도쿄 도심부는 온난 습윤 기후이다.\n\n"
                                    "{| class=\"wikitable\"\n|+ 도쿄의 기후\n! 월 !! 1월\n|-\n! 평균 기온\n| 5.4\n|}\n"
                                ),
                            },
                        },
                    },
                ],
            },
        }

    def fetch_page(self, lang: str, title: str) -> dict[str, JsonValue]:
        return {"query": {"pages": [self._pages[(lang, title)]]}}

    def fetch_pages(self, lang: str, titles: list[str]) -> dict[str, dict[str, JsonValue]]:
        return {title: self.fetch_page(lang, title) for title in titles}


class InvalidEnglishLanglinkClient(TokyoPrefectureClient):
    def __init__(self) -> None:
        super().__init__()
        self._pages[("ko", CHIYODA_KO_TITLE)]["langlinks"] = [
            {"lang": "en", "title": "Category:Chiyoda, Tokyo"},
            {"lang": "en", "title": "千代田区"},
            {"lang": "en", "title": "Chiyoda, Tokyo"},
            {"lang": "ja", "title": "千代田区"},
        ]


class CityWeatherClient(TokyoPrefectureClient):
    def __init__(self) -> None:
        super().__init__()
        self._pages[("ko", CHIYODA_KO_TITLE)]["revisions"] = [
            {
                "slots": {
                    "main": {
                        "content": (
                            "'''지요다구'''는 일본 도쿄도의 특별구이다.\n\n"
                            "== 기후 ==\n지요다구 도심 기후이다.\n\n"
                            "{| class=\"wikitable\"\n"
                            "|+ 지요다구의 기후\n"
                            "! 월 !! 1월\n"
                            "|-\n"
                            "! 평균 기온\n"
                            "| 5.5\n"
                            "|}\n"
                        ),
                    },
                },
            },
        ]


class TokyoPrefectureEnrichmentTest(unittest.TestCase):
    def test_html_langlinks_use_canonical_language_selector_when_extra_hreflang_links_exist(self) -> None:
        html = (
            "<html><body>"
            "<h1 id=\"firstHeading\">지요다구</h1>"
            "<div class=\"mw-parser-output\"><p>지요다구는 일본 도쿄도의 특별구이다.</p></div>"
            "<a href=\"/wiki/Category:Chiyoda,_Tokyo\" hreflang=\"en\">분류 영어</a>"
            "<a href=\"/wiki/千代田区\" hreflang=\"en\">잘못된 영어 앵커</a>"
            "<nav id=\"p-lang\"><ul>"
            "<li class=\"interlanguage-link interwiki-en\">"
            "<a href=\"https://en.wikipedia.org/wiki/Chiyoda,_Tokyo\" hreflang=\"en\">English</a>"
            "</li>"
            "<li class=\"interlanguage-link interwiki-ja\">"
            "<a href=\"https://ja.wikipedia.org/wiki/千代田区\" hreflang=\"ja\">日本語</a>"
            "</li>"
            "</ul></nav>"
            "</body></html>"
        )

        page = parse_wikipedia_html("ko", CHIYODA_KO_TITLE, html)

        self.assertEqual(
            [{"lang": "en", "title": "Chiyoda, Tokyo"}, {"lang": "ja", "title": "千代田区"}],
            page["langlinks"],
        )

    def test_html_parser_promotes_legacy_h3_subsections_for_weather(self) -> None:
        html = (
            "<html><body>"
            "<h1 id=\"firstHeading\">도쿄도</h1>"
            "<div id=\"mw-content-text\"><div class=\"mw-parser-output\">"
            "<p>도쿄도는 일본의 광역자치단체이다.</p>"
            "<h2><span class=\"mw-headline\" id=\"지리\">지리</span></h2>"
            "<p>도쿄도는 간토 지방 남부에 위치한다.</p>"
            "<h3><span class=\"mw-headline\" id=\"기후\">기후</span></h3>"
            "<p>도쿄 도심부는 온난 습윤 기후이다.</p>"
            "</div></div>"
            "</body></html>"
        )

        page = parse_wikipedia_html("ko", TOKYO_KO_TITLE, html)
        content = page["revisions"][0]["slots"]["main"]["content"]

        self.assertIn("== 지리 ==\n도쿄도는 간토 지방 남부에 위치한다.", content)
        self.assertIn("== 기후 ==\n도쿄 도심부는 온난 습윤 기후이다.", content)

    def test_html_parser_keeps_nested_parsoid_weather_section_separate(self) -> None:
        html = (
            "<html><body>"
            "<h1 id=\"firstHeading\">도쿄도</h1>"
            "<div id=\"mw-content-text\"><div class=\"mw-parser-output\">"
            "<section data-mw-section-id=\"0\"><p>도쿄도는 일본의 광역자치단체이다.</p></section>"
            "<section data-mw-section-id=\"4\">"
            "<div class=\"mw-heading mw-heading2\"><h2 id=\"지리\">지리</h2></div>"
            "<p>도쿄도는 간토 지방 남부에 위치한다.</p>"
            "<section data-mw-section-id=\"5\">"
            "<div class=\"mw-heading mw-heading3\"><h3 id=\"기후\">기후</h3></div>"
            "<p>도쿄 도심부는 온난 습윤 기후이다.</p>"
            "</section>"
            "</section>"
            "</div></div>"
            "</body></html>"
        )

        page = parse_wikipedia_html("ko", TOKYO_KO_TITLE, html)
        content = page["revisions"][0]["slots"]["main"]["content"]

        self.assertIn("== 지리 ==\n도쿄도는 간토 지방 남부에 위치한다.", content)
        self.assertIn("== 기후 ==\n도쿄 도심부는 온난 습윤 기후이다.", content)

    def test_korean_source_uses_first_valid_english_langlink_for_city_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _, cities = acquire_city_data(
                titles=[PageTarget(title=CHIYODA_KO_TITLE, lang="ko", prefecture_id="JP-13")],
                output_dir=Path(tmpdir),
                client=InvalidEnglishLanglinkClient(),
            )

        self.assertEqual("Chiyoda, Tokyo", cities[0].city_name_en)
        self.assertEqual("JP-13-CHIYODA-TOKYO", cities[0].city_id)

    def test_tokyo_prefecture_record_is_enriched_from_korean_wikipedia_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            prefectures, _ = acquire_city_data(
                titles=[PageTarget(title=CHIYODA_KO_TITLE, lang="ko", prefecture_id="JP-13")],
                output_dir=output_dir,
                client=TokyoPrefectureClient(),
            )

            tokyo = prefectures[0]
            payload = json.loads((output_dir / "prefectures.json").read_text(encoding="utf-8"))[0]

        self.assertEqual("https://ko.wikipedia.org/wiki/%EB%8F%84%EC%BF%84%EB%8F%84", tokyo.source_url)
        self.assertEqual("도쿄도는 일본의 수도권에 있는 광역자치단체이다.", tokyo.description)
        self.assertIn("간토 지방 남부", tokyo.geography_description)
        self.assertEqual("도쿄의 기후", tokyo.climate_table["caption"])
        self.assertEqual("collected", tokyo.field_status["geography_description"])
        self.assertEqual("collected", tokyo.field_status["climate_table"])
        self.assertEqual(tokyo.geography_description, payload["geography_description"])
        self.assertEqual(tokyo.climate_table, payload["climate_table"])

    def test_missing_city_weather_uses_tokyo_prefecture_climate_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            _, cities = acquire_city_data(
                titles=[PageTarget(title=CHIYODA_KO_TITLE, lang="ko", prefecture_id="JP-13")],
                output_dir=output_dir,
                client=TokyoPrefectureClient(),
            )

            payload = json.loads((output_dir / "cities.json").read_text(encoding="utf-8"))[0]

        city = cities[0]
        if city.climate_table is None:
            self.fail("City climate_table should be inherited from Tokyo Prefecture.")

        self.assertEqual("collected", city.field_status["climate_table"])
        self.assertEqual("도쿄의 기후", city.climate_table["caption"])
        self.assertEqual("https://ko.wikipedia.org/wiki/%EB%8F%84%EC%BF%84%EB%8F%84", city.climate_table["source_url"])
        self.assertIn("온난 습윤 기후", city.climate_table["content"])
        self.assertEqual("collected", payload["field_status"]["climate_table"])
        self.assertEqual(city.climate_table, payload["climate_table"])

    def test_city_specific_weather_is_not_overwritten_by_prefecture_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _, cities = acquire_city_data(
                titles=[PageTarget(title=CHIYODA_KO_TITLE, lang="ko", prefecture_id="JP-13")],
                output_dir=Path(tmpdir),
                client=CityWeatherClient(),
            )

        city = cities[0]
        if city.climate_table is None:
            self.fail("City climate_table should be collected from the city page.")

        self.assertEqual("collected", city.field_status["climate_table"])
        self.assertEqual("지요다구의 기후", city.climate_table["caption"])
        self.assertNotIn("source_scope", city.climate_table)


if __name__ == "__main__":
    unittest.main()
