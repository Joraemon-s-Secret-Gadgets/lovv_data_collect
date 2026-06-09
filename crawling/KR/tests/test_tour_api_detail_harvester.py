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
            "attractions": [{"contentid": "1"}],
            "festivals": [{"contentid": "2"}],
        }
        result = normalize_city_detail(city, payload, Path("sample.json"), None)
        self.assertEqual("KR-47-ANDONG", result["city_id"])
        self.assertEqual("ANDONG", result["city_name_en"])
        self.assertEqual(2, result["attractions_count_filtered"])
        self.assertEqual(1, result["festivals_count_filtered"])
        self.assertEqual(1, len(result["attractions"]))
        self.assertEqual(1, len(result["festivals"]))

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
            self.assertEqual("KR-47-ANDONG", saved["city_id"])
            self.assertEqual("ANDONG", saved["city_name_en"])
            self.assertEqual(1, len(saved["attractions"]))


if __name__ == "__main__":
    unittest.main()
