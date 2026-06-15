"""Tests for image S3 key generation."""

from __future__ import annotations

import unittest

from kr_image_uploader.s3_keys import build_image_key, safe_name


class S3KeysTest(unittest.TestCase):
    def test_safe_name_removes_unsafe_characters(self) -> None:
        self.assertEqual("Wonju_City", safe_name("Wonju City"))
        self.assertEqual("UNKNOWN", safe_name("###"))

    def test_build_image_key(self) -> None:
        self.assertEqual(
            "images/KR/Cheorwon/Goseokjeong_1.jpg",
            build_image_key("Cheorwon", "Goseokjeong", "1", ".jpg"),
        )

    def test_build_image_key_normalizes_extension(self) -> None:
        self.assertEqual(
            "images/KR/Cheorwon/Pochungsa_2.jpg",
            build_image_key("Cheorwon", "Pochungsa", "2", "JPG"),
        )
        self.assertEqual(
            "images/KR/Cheorwon/X_1.jpg",
            build_image_key("Cheorwon", "X", "1", ""),
        )

    def test_build_image_key_custom_prefix(self) -> None:
        self.assertEqual(
            "images/KR/Pohang/A_1.png",
            build_image_key("Pohang", "A", "1", "png", prefix="images/KR"),
        )


if __name__ == "__main__":
    unittest.main()
