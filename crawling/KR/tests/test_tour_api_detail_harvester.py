"""Tests for tour_api_detail_harvester utility functions and extraction flow."""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from crawling.KR.tour_api_detail_harvester import (
    CityTarget,
    _candidate_basenames,
    _contains_city_signature,
    normalize_city_detail,
    extract_city_details,
    find_city_source_paths,
)


class TourApiDetailHarvesterTest(unittest.TestCase):
    def test_candidate_basenames_normalization(self) -> None:
        city = CityTarget(
            city_id="KR-47-ANDONG",
            city_name_ko="안동시",
            city_name_en="Andong City",
            prefecture_id="KR-47",
        )
        names = _candidate_basenames(city)
        self.assertIn("Andong City", names)
        self.assertIn("Andong_City", names)
        self.assertIn("KR-47-ANDONG", names)
        self.assertIn("KR-47-ANDONG".lower(), names)

    def test_contains_city_signature_from_meta(self) -> None:
        city = CityTarget(
            city_id="KR-47-ANDONG",
            city_name_ko="안동시",
            city_name_en="ANDONG",
            prefecture_id="KR-47",
        )
        payload = {
            "meta": {
                "city_name_en": "ANDONG",
                "city_name_ko": "안동시",
            }
        }
        self.assertTrue(_contains_city_signature(payload, city))

    def test_normalize_city_detail_includes_payload_counts(self) -> None:
        city = CityTarget(
            city_id="KR-47-ANDONG",
            city_name_ko="안동시",
            city_name_en="ANDONG",
            prefecture_id="KR-47",
        )
        payload = {
            "meta": {
                "city_name_en": "ANDONG",
                "city_name_ko": "안동시",
                "province": "경상북도",
            },
            "attractions_count_filtered": 2,
            "festivals_count_filtered": 1,
            "attractions": [{"contentid": "1", "title": "개목사(안동)"}],
            "festivals": [{"contentid": "2"}],
        }
        result = normalize_city_detail(city, payload, Path("sample.json"), None)
        self.assertEqual("KR-47-ANDONG", result["meta"]["city_id"])
        self.assertEqual("ANDONG", result["meta"]["city_name_en"])
        self.assertEqual(2, result["attractions_count_filtered"])
        self.assertEqual(1, result["festivals_count_filtered"])
        self.assertEqual(1, len(result["attractions"]))
        self.assertEqual(1, len(result["festivals"]))
        self.assertEqual("collected", result["attractions"][0]["field_status"]["name"])

    def test_normalize_city_detail_splits_raw_items_by_content_type(self) -> None:
        city = CityTarget(
            city_id="KR-47-ANDONG",
            city_name_ko="안동시",
            city_name_en="ANDONG",
            prefecture_id="KR-47",
        )
        payload = {
            "meta": {"city_name_en": "ANDONG", "city_name_ko": "안동시"},
            "items": [
                {
                    "contentid": "a1",
                    "contenttypeid": "12",
                    "title": "관광지",
                    "addr1": "경상북도 안동시",
                    "mapx": "128.1",
                    "mapy": "36.1",
                    "_assigned_theme": "역사·전통",
                    "detail": {"common": {"title": "관광지"}},
                },
                {
                    "contentid": "f1",
                    "contenttypeid": "15",
                    "title": "축제",
                    "addr1": "경상북도 안동시",
                    "mapx": "128.2",
                    "mapy": "36.2",
                    "detail": {"common": {"title": "축제"}},
                },
            ],
        }
        result = normalize_city_detail(city, payload, None, None)
        self.assertEqual(1, len(result["attractions"]))
        self.assertEqual(1, len(result["festivals"]))
        self.assertEqual("a1", result["attractions"][0]["contentid"])
        self.assertEqual("f1", result["festivals"][0]["contentid"])
        self.assertEqual("collected", result["attractions"][0]["field_status"]["coordinates"])

    def test_normalize_city_detail_attaches_cached_detail_files(self) -> None:
        city = CityTarget(
            city_id="KR-47-ANDONG",
            city_name_ko="안동시",
            city_name_en="ANDONG",
            prefecture_id="KR-47",
        )
        payload = {
            "meta": {"city_name_en": "ANDONG", "city_name_ko": "안동시"},
            "attractions": [
                {
                    "contentid": "126157",
                    "contenttypeid": "12",
                    "title": "개목사(안동)",
                    "addr1": "경상북도 안동시",
                    "mapx": "128.6679838568",
                    "mapy": "36.6579094974",
                }
            ],
            "festivals": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            detail_dir = Path(tmpdir) / "detail"
            detail_dir.mkdir()
            (detail_dir / "126157.json").write_text(
                json.dumps(
                    {
                        "common": {"contentid": "126157", "title": "개목사(안동)"},
                        "intro": {"infocenter": "054-000-0000"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = normalize_city_detail(city, payload, None, None, detail_dir)

        detail = result["attractions"][0]["detail"]
        self.assertEqual("126157", detail["common"]["contentid"])
        self.assertEqual("054-000-0000", detail["intro"]["infocenter"])
        self.assertEqual("collected", result["attractions"][0]["field_status"]["detail"])

    def test_extract_city_details_outputs_json_file(self) -> None:
        city = CityTarget(
            city_id="KR-47-ANDONG",
            city_name_ko="안동시",
            city_name_en="ANDONG",
            prefecture_id="KR-47",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            raw = repo_root / "data/raw/final"
            raw.mkdir(parents=True)
            (raw / "andong.json").write_text(
                json.dumps(
                    {
                        "meta": {"city_name_en": "ANDONG", "city_name_ko": "안동시"},
                        "attractions": [{"contentid": "a1"}],
                        "festivals": [{"contentid": "f1"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            outdir = Path(tmpdir) / "out"
            results = extract_city_details(
                city_targets=[city],
                repo_path=repo_root,
                output_dir=outdir,
                overwrite=False,
                dry_run=False,
            )

            output_path = outdir / "andong.json"
            self.assertEqual(1, len(results))
            self.assertTrue(output_path.exists())

            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("KR-47-ANDONG", saved["meta"]["city_id"])
            self.assertEqual("ANDONG", saved["meta"]["city_name_en"])
            self.assertEqual(1, len(saved["attractions"]))

    def test_find_city_source_paths_supports_list_by_city_filtered_files(self) -> None:
        city = CityTarget(
            city_id="KR-47-ANDONG",
            city_name_ko="안동시",
            city_name_en="ANDONG",
            prefecture_id="KR-47",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            list_by_city = repo_root / "data/raw/list_by_city"
            list_by_city.mkdir(parents=True)
            expected = list_by_city / "andong_filtered.json"
            expected.write_text(
                json.dumps(
                    {
                        "meta": {"city_name_en": "ANDONG", "city_name_ko": "안동시"},
                        "attractions": [],
                        "festivals": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            matches = find_city_source_paths(repo_root, city)

        self.assertEqual([expected], matches)


if __name__ == "__main__":
    unittest.main()
