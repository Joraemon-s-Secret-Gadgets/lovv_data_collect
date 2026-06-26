"""Tests for Wikipedia-first South Korea city data acquisition."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

from crawling.KR.city_wikipedia_acquisition import (
    main,
    parse_args,
)
from crawling.KR.pipeline import PageTarget, load_targets, acquire_city_data
from crawling.KR.wikipedia_client import WikipediaHtmlClient, parse_wikipedia_html
from crawling.KR.normalizer import (
    build_city_record,
    build_prefecture_record,
    _geocode_nominatim,
)
from crawling.KR.provinces import detect_province, find_province


class FakeWikipediaClient:
    def __init__(self) -> None:
        self.pages: dict[tuple[str, str], dict[str, Any]] = {
            ("ko", "춘천시"): {
                "query": {
                    "pages": [
                        {
                            "title": "춘천시",
                            "extract": "춘천시는 대한민국 강원특별자치도의 도청 소재지이다.",
                            "coordinates": [{"lat": 37.8813, "lon": 127.7298}],
                            "extlinks": [
                                {"url": "https://www.chuncheon.go.kr/"},
                                {"url": "https://tour.chuncheon.go.kr/"}
                            ],
                            "langlinks": [],
                            "revisions": [
                                {
                                    "slots": {
                                        "main": {
                                            "content": "== 지리 ==\n춘천시의 지리적 환경은 영서 지방에 위치해 있으며...\n\n== 기후 ==\n{| class=\"wikitable\"\n|+ 기후표\n! 월 !! 1월\n|-\n! 최고\n| 1.0\n|}",
                                        }
                                    }
                                }
                            ],
                        }
                    ]
                }
            },
            ("ko", "구미시"): {
                "query": {
                    "pages": [
                        {
                            "title": "구미시",
                            "extract": "구미시는 대한민국 경상북도 중서부에 있는 도시이다.",
                            "coordinates": [],
                            "extlinks": [
                                {"url": "https://www.gumi.go.kr/"},
                                {"url": "https://geohack.toolforge.org/geohack.php?pagename=%EA%B5%AC%EB%AF%B8%EC%8B%9C&params=36.1194_N_128.3444_E_type:city"}
                            ],
                            "langlinks": [],
                            "revisions": [],
                        }
                    ]
                }
            },
            ("ko", "고성군 (강원특별자치도)"): {
                "query": {
                    "pages": [
                        {
                            "title": "고성군 (강원특별자치도)",
                            "extract": "고성군은 대한민국 강원특별자치도에 위치한 군이다.",
                            "coordinates": [],
                            "extlinks": [
                                {"url": "https://www.gwgs.go.kr/"}
                            ],
                            "langlinks": [],
                            "revisions": [],
                        }
                    ]
                }
            },
        }

    def fetch_page(self, lang: str, title: str) -> dict[str, Any]:
        return self.pages.get((lang, title), {"query": {"pages": [{"title": title, "missing": ""}]}})

    def fetch_pages(self, lang: str, titles: list[str]) -> dict[str, dict[str, Any]]:
        return {title: self.fetch_page(lang, title) for title in titles}


class BatchExtractOmittingClient(FakeWikipediaClient):
    def fetch_pages(self, lang: str, titles: list[str]) -> dict[str, dict[str, Any]]:
        payloads: dict[str, dict[str, Any]] = {}
        for title in titles:
            page = dict(self.pages[(lang, title)]["query"]["pages"][0])
            page.pop("extract", None)
            page["revisions"] = [
                {
                    "slots": {
                        "main": {
                            "content": "춘천시는 대한민국 강원특별자치도의 도청 소재지이다.",
                        }
                    }
                }
            ]
            payloads[title] = {"query": {"pages": [page]}}
        return payloads


class CityWikipediaAcquisitionKRTest(unittest.TestCase):
    def test_html_client_uses_requests_session_for_page_fetching(self) -> None:
        class FakeResponse:
            text = "<html><body><h1 id=\"firstHeading\">춘천시</h1><div class=\"mw-parser-output\"><p>춘천시는 강원특별자치도의 도시이다.</p></div></body></html>"

            def raise_for_status(self) -> None:
                return None

        class FakeSession:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, str], int]] = []

            def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
                self.calls.append((url, headers, timeout))
                return FakeResponse()

        session = FakeSession()
        client = WikipediaHtmlClient(session=session, request_delay_seconds=0, timeout=7)

        payload = client.fetch_page("ko", "춘천시")

        page = payload["query"]["pages"][0]
        self.assertEqual("춘천시", page["title"])
        self.assertEqual("춘천시는 강원특별자치도의 도시이다.", page["extract"])
        self.assertEqual(1, len(session.calls))
        self.assertIn("ko.wikipedia.org/wiki/", session.calls[0][0])
        self.assertEqual(7, session.calls[0][2])

    def test_parse_wikipedia_html_extracts_lead_coordinates_links_and_sections(self) -> None:
        html = """
        <html>
          <body>
            <h1 id="firstHeading">춘천시</h1>
            <div class="mw-parser-output"><span class="geo-dec">0; 0</span></div>
            <div id="mw-content-text">
              <div class="mw-parser-output">
                <p><b>춘천시</b>는 대한민국 강원특별자치도에 위치한 도시이다.</p>
                <p>도청 소재지이기도 하다.</p>
                <span class="geo-dec">37.8813; 127.7298</span>
                <h2><span class="mw-headline" id="지리">지리</span></h2>
                <p>춘천시는 산악 지대로 둘러싸여 있다.</p>
                <h2><span class="mw-headline" id="기후">기후</span></h2>
                <p>기온 차이가 크다.</p>
                <table class="wikitable">
                  <caption>춘천의 기후</caption>
                  <tr>
                    <th>월</th>
                    <th>1월</th><th>2월</th><th>3월</th><th>4월</th><th>5월</th><th>6월</th>
                    <th>7월</th><th>8월</th><th>9월</th><th>10월</th><th>11월</th><th>12월</th><th>연간</th>
                  </tr>
                  <tr>
                    <td>평균 기온</td>
                    <td>-4.6</td><td>-2.0</td><td>3.5</td><td>11.0</td><td>17.0</td><td>21.5</td>
                    <td>24.5</td><td>25.0</td><td>20.0</td><td>13.0</td><td>5.5</td><td>-1.5</td><td>11.4</td>
                  </tr>
                </table>
                <p><a class="external text" href="https://www.chuncheon.go.kr/">공식 누리집</a></p>
              </div>
            </div>
            <a href="/wiki/Chuncheon" hreflang="en">English</a>
          </body>
        </html>
        """

        page = parse_wikipedia_html("ko", "춘천시", html)

        self.assertEqual("춘천시", page["title"])
        self.assertEqual(
            "춘천시는 대한민국 강원특별자치도에 위치한 도시이다.\n\n도청 소재지이기도 하다.",
            page["extract"],
        )
        self.assertEqual([{"lat": 37.8813, "lon": 127.7298}], page["coordinates"])
        self.assertEqual([{"url": "https://www.chuncheon.go.kr/"}], page["extlinks"])
        self.assertIn({"lang": "en", "title": "Chuncheon"}, page["langlinks"])
        self.assertIsNotNone(page.get("climate_table"))
        self.assertEqual("춘천의 기후", page["climate_table"]["caption"])
        self.assertIn("class=\"wikitable\"", page["climate_table"]["wikitext"])
        self.assertIsNotNone(page["climate_table"].get("data"))
        self.assertEqual("-4.6", page["climate_table"]["data"]["1월"]["평균 기온"])
        content = page["revisions"][0]["slots"]["main"]["content"]
        self.assertIn("== 지리 ==\n춘천시는 산악 지대로 둘러싸여 있다.", content)
        self.assertIn("== 기후 ==\n기온 차이가 크다.", content)

    def test_parse_wikipedia_html_fallback_geohack(self) -> None:
        html = """
        <html>
          <body>
            <h1 id="firstHeading">구미시</h1>
            <div id="mw-content-text">
              <div class="mw-parser-output">
                <p>구미시 내용</p>
                <a href="https://geohack.toolforge.org/geohack.php?pagename=%EA%B5%AC%EB%AF%B8%EC%8B%9C&params=36.1194_N_128.3444_E_type:city">지도</a>
              </div>
            </div>
          </body>
        </html>
        """
        page = parse_wikipedia_html("ko", "구미시", html)
        self.assertEqual([{"lat": 36.1194, "lon": 128.3444}], page["coordinates"])

    def test_detect_province_from_text(self) -> None:
        self.assertEqual("KR-42", detect_province(["이 곳은 강원특별자치도 춘천시입니다."]).prefecture_id)
        self.assertEqual("KR-47", detect_province(["Located in Gyeongsangbuk-do area."]).prefecture_id)
        self.assertEqual("KR-11", detect_province(["서울특별시에 있습니다."]).prefecture_id)
        self.assertIsNone(detect_province(["관련 없는 텍스트입니다."]))

    def test_find_province_by_id(self) -> None:
        self.assertEqual("경상북도", find_province("KR-47").name_ko)
        self.assertIsNone(find_province("KR-99"))

    def test_build_city_record_for_chuncheon(self) -> None:
        client = FakeWikipediaClient()
        page = client.fetch_page("ko", "춘천시")["query"]["pages"][0]
        pages = {
            "source": page,
            "ko": page,
            "ja": {},
            "en": {},
        }
        
        city = build_city_record(pages, "2026-06-07T00:00:00+09:00", fallback_prefecture_id="KR-42")
        self.assertEqual("KR-42-CHUNCHEON", city.city_id)
        self.assertEqual("KR-42", city.prefecture_id)
        self.assertEqual(37.8813, city.latitude)
        self.assertEqual(127.7298, city.longitude)
        self.assertEqual("춘천시", city.city_name_ko)
        self.assertEqual("", city.city_name_ja)
        self.assertEqual("CHUNCHEON", city.city_name_en)
        self.assertEqual("대한민국 강원특별자치도", city.location)
        self.assertEqual("collected", city.field_status["city_name_ko"])
        self.assertEqual("missing", city.field_status["city_name_ja"])
        self.assertEqual("collected", city.field_status["city_name_en"])
        self.assertEqual("collected", city.field_status["climate_table"])
        self.assertEqual("기후표", city.climate_table["caption"])
        self.assertIn("춘천시의 지리적 환경은", city.geography_description)

    def test_build_city_record_prioritizes_pre_extracted_climate_table(self) -> None:
        page = {
            "title": "춘천시",
            "climate_table": {
                "caption": "춘천의 기후",
                "wikitext": "{| class=\"wikitable\"\n|}",
                "data": {
                    "1월": {
                        "평균 기온": "-4.6"
                    }
                }
            }
        }
        pages = {
            "source": page,
            "ko": page,
            "ja": {},
            "en": {},
        }
        city = build_city_record(pages, "2026-06-07T00:00:00+09:00", fallback_prefecture_id="KR-42")
        self.assertEqual("collected", city.field_status["climate_table"])
        self.assertEqual("춘천의 기후", city.climate_table["caption"])
        self.assertEqual("{| class=\"wikitable\"\n|}", city.climate_table["wikitext"])
        self.assertEqual("-4.6", city.climate_table["data"]["1월"]["평균 기온"])

    def test_build_city_record_geohack_parsing_for_gumi(self) -> None:
        client = FakeWikipediaClient()
        page = client.fetch_page("ko", "구미시")["query"]["pages"][0]
        pages = {
            "source": page,
            "ko": page,
            "ja": {},
            "en": {},
        }
        
        city = build_city_record(pages, "2026-06-07T00:00:00+09:00", fallback_prefecture_id="KR-47")
        self.assertEqual("KR-47-GUMI", city.city_id)
        self.assertEqual("KR-47", city.prefecture_id)
        self.assertAlmostEqual(36.1194, city.latitude or 0, places=4)
        self.assertAlmostEqual(128.3444, city.longitude or 0, places=4)
        self.assertEqual("collected", city.field_status["latitude"])

    @patch("crawling.KR.normalizer._geocode_nominatim")
    def test_build_city_record_nominatim_fallback(self, mock_geocode: MagicMock) -> None:
        mock_geocode.return_value = (38.3798, 128.4681)
        client = FakeWikipediaClient()
        page = client.fetch_page("ko", "고성군 (강원특별자치도)")["query"]["pages"][0]
        pages = {
            "source": page,
            "ko": page,
            "ja": {},
            "en": {},
        }
        
        city = build_city_record(pages, "2026-06-07T00:00:00+09:00", fallback_prefecture_id="KR-42")
        self.assertEqual("KR-42-GOSEONG-GANGWON", city.city_id)
        self.assertEqual(38.3798, city.latitude)
        self.assertEqual(128.4681, city.longitude)
        self.assertEqual("collected", city.field_status["latitude"])
        self.assertEqual("collected", city.field_status["longitude"])
        mock_geocode.assert_called_once_with("대한민국 강원특별자치도 고성군")

    @patch("crawling.KR.normalizer.requests.get")
    @patch("crawling.KR.normalizer.time.sleep")
    def test_geocode_nominatim_success(self, mock_sleep: MagicMock, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = [{"lat": "37.1234", "lon": "128.5678"}]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        coords = _geocode_nominatim("대한민국 경상북도 구미시")
        self.assertEqual((37.1234, 128.5678), coords)
        mock_get.assert_called_once()
        mock_sleep.assert_called_once_with(1.0)

    def test_build_prefecture_record(self) -> None:
        province = find_province("KR-42")
        self.assertIsNotNone(province)
        record = build_prefecture_record(
            province=province,
            collected_at="2026-06-07T00:00:00+09:00",
            source_url="https://ko.wikipedia.org/wiki/춘천시",
        )
        self.assertEqual("KR-42", record.prefecture_id)
        self.assertEqual("강원특별자치도", record.name_ko)
        self.assertEqual("", record.name_ja)
        self.assertEqual("Gangwon State", record.name_en)
        self.assertEqual("Gangwon", record.region)
        self.assertEqual("collected", record.field_status["name_ko"])
        self.assertEqual("missing", record.field_status["name_ja"])

    def test_load_targets_from_list_and_file(self) -> None:
        targets = load_targets(None, ["춘천시", "구미시"], default_lang="ko", default_prefecture_id="KR-42")
        self.assertEqual(2, len(targets))
        self.assertEqual("춘천시", targets[0].title)
        self.assertEqual("ko", targets[0].lang)
        self.assertEqual("KR-42", targets[0].prefecture_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "targets.json"
            file_path.write_text(json.dumps([
                "원주시",
                {"title": "경주시", "prefecture_id": "KR-47"}
            ]), encoding="utf-8")
            
            targets_from_file = load_targets(file_path, [], default_lang="ko", default_prefecture_id="KR-42")
            self.assertEqual(2, len(targets_from_file))
            self.assertEqual("원주시", targets_from_file[0].title)
            self.assertEqual("KR-42", targets_from_file[0].prefecture_id)
            self.assertEqual("경주시", targets_from_file[1].title)
            self.assertEqual("KR-47", targets_from_file[1].prefecture_id)

    def test_acquire_city_data_merges_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            # Write pre-existing data
            prefectures_file = output_dir / "prefectures.json"
            cities_file = output_dir / "cities.json"
            
            prefectures_file.write_text(json.dumps([{
                "prefecture_id": "KR-47",
                "name_ko": "경상북도",
                "name_ja": "",
                "name_en": "Gyeongsangbuk-do",
                "region": "Yeongnam",
                "source_name": "Wikipedia",
                "source_url": "https://ko.wikipedia.org/wiki/경주시",
                "collected_at": "2026-06-07T00:00:00+09:00",
                "field_status": {}
            }]), encoding="utf-8")
            
            cities_file.write_text(json.dumps([{
                "city_id": "KR-47-GYEONGJU",
                "city_name_ko": "경주시",
                "city_name_ja": "",
                "city_name_en": "GYEONGJU",
                "prefecture_id": "KR-47",
                "location": "대한민국 경상북도",
                "latitude": 35.8562,
                "longitude": 129.213,
                "description": "경주시는 경상북도의 도시이다.",
                "geography_description": "",
                "climate_table": None,
                "site_urls": ["https://www.gyeongju.go.kr/"],
                "source_name": "Wikipedia",
                "source_url": "https://ko.wikipedia.org/wiki/경주시",
                "collected_at": "2026-06-07T00:00:00+09:00",
                "field_status": {}
            }]), encoding="utf-8")
            
            # Now run acquire_city_data on a new city (춘천시)
            client = FakeWikipediaClient()
            prefectures, cities = acquire_city_data(
                titles=["춘천시"],
                output_dir=output_dir,
                client=client,
                source_lang="ko"
            )
            
            # Check that both existing (경주시) and new (춘천시) are present and sorted
            self.assertEqual(2, len(prefectures))
            self.assertEqual(2, len(cities))
            
            self.assertEqual("KR-42", prefectures[0].prefecture_id)
            self.assertEqual("KR-47", prefectures[1].prefecture_id)
            
            self.assertEqual("KR-42-CHUNCHEON", cities[0].city_id)
            self.assertEqual("KR-47-GYEONGJU", cities[1].city_id)

    @patch("crawling.KR.city_wikipedia_acquisition.WikipediaHtmlClient")
    @patch("crawling.KR.city_wikipedia_acquisition.acquire_city_data")
    def test_cli_entrypoint(self, mock_acquire: MagicMock, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        args = parse_args(["춘천시", "구미시", "--output-dir", "test_output"])
        self.assertEqual(["춘천시", "구미시"], args.titles)
        self.assertEqual(Path("test_output"), args.output_dir)
        self.assertEqual("html", args.fetcher)
        
        # Test main function
        with patch("crawling.KR.city_wikipedia_acquisition.load_targets") as mock_load:
            targets = [PageTarget("춘천시", "ko", "")]
            mock_load.return_value = targets
            
            exit_code = main(["춘천시", "--output-dir", "test_output"])
            self.assertEqual(0, exit_code)
            mock_acquire.assert_called_once_with(
                titles=targets,
                output_dir=Path("test_output"),
                client=mock_client,
                source_lang="ko"
            )


if __name__ == "__main__":
    unittest.main()
