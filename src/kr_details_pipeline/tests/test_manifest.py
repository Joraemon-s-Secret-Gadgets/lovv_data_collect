"""Tests for raw manifest creation."""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from kr_details_pipeline.manifest import build_raw_manifest, sha256_file


class ManifestTest(unittest.TestCase):
    def test_build_raw_manifest_reads_city_counts_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            input_dir = Path(tmpdir)
            city_file = input_dir / "Chuncheon.json"
            city_file.write_text(
                json.dumps(
                    {
                        "meta": {
                            "city_name_en": "CHUNCHEON",
                            "city_name_ko": "춘천시",
                            "province": "강원특별자치도",
                        },
                        "attractions": [{"contentid": "1"}],
                        "festivals": [{"contentid": "2"}],
                        "visitor_statistics": [{"month": "202501"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            expected_checksum = sha256_file(city_file)
            records = build_raw_manifest(input_dir, "20260609")

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("CHUNCHEON", record.city_name_en)
        self.assertEqual("춘천시", record.city_name_ko)
        self.assertEqual(1, record.attraction_count)
        self.assertEqual(1, record.festival_count)
        self.assertEqual(1, record.visitor_statistics_count)
        self.assertEqual(expected_checksum, record.checksum_sha256)
        self.assertEqual("raw/KR/details/20260609/CHUNCHEON.json", record.s3_key)


if __name__ == "__main__":
    unittest.main()
