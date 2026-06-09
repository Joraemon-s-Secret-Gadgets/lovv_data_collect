"""Tests for S3 key generation."""

from __future__ import annotations

import unittest

from kr_details_pipeline.s3_keys import build_raw_detail_key, safe_city_name


class S3KeysTest(unittest.TestCase):
    def test_safe_city_name_removes_unsafe_characters(self) -> None:
        self.assertEqual("Wonju_City", safe_city_name("Wonju City"))
        self.assertEqual("UNKNOWN_CITY", safe_city_name("###"))

    def test_build_raw_detail_key_accepts_date_formats(self) -> None:
        self.assertEqual(
            "raw/KR/details/20260609/CHUNCHEON.json",
            build_raw_detail_key("CHUNCHEON", "2026-06-09"),
        )
        self.assertEqual(
            "raw/KR/details/20260609/WONJU.json",
            build_raw_detail_key("WONJU", "20260609"),
        )

    def test_build_raw_detail_key_rejects_bad_date(self) -> None:
        with self.assertRaises(ValueError):
            build_raw_detail_key("WONJU", "2026/06/09")


if __name__ == "__main__":
    unittest.main()
