"""Tests for image target extraction."""

from __future__ import annotations

import unittest

from kr_image_uploader.extract import collect_image_targets

_PAYLOAD = {
    "attractions": [
        {
            "contentid": "2615225",
            "title": "고석정",
            "firstimage": "http://x/a_2.jpg",
            "firstimage2": "http://x/a_3.jpg",
        },
        {
            "contentid": "125759",
            "title": "도피안사(철원)",
            "firstimage": "http://x/b_2.jpg",
            "firstimage2": "",          # empty -> skipped
        },
        {
            "contentid": "999",
            "title": "고석정",            # duplicate title -> disambiguated
            "firstimage": "http://x/c_2.jpg",
            "firstimage2": "",
        },
    ],
    "festivals": [
        {
            "contentid": "1882134",
            "title": "철원 한탄강 얼음트레킹 축제",
            "firstimage": "http://x/f_2.jpg",
            "firstimage2": "http://x/f_3.jpg",
        }
    ],
}


class ExtractTest(unittest.TestCase):
    def test_counts_only_non_empty_images(self) -> None:
        targets = collect_image_targets(_PAYLOAD)
        # a:2 + b:1 + c:1 + festival:2 = 6
        self.assertEqual(6, len(targets))

    def test_names_and_suffixes(self) -> None:
        targets = collect_image_targets(_PAYLOAD)
        names = {(t.name, t.suffix) for t in targets}
        self.assertIn(("Goseokjeong", "1"), names)
        self.assertIn(("Goseokjeong", "2"), names)
        self.assertIn(("Dopiansa", "1"), names)
        # duplicate "고석정" gets contentid appended
        self.assertIn(("Goseokjeong_999", "1"), names)

    def test_handles_missing_groups(self) -> None:
        self.assertEqual([], collect_image_targets({}))
        self.assertEqual([], collect_image_targets({"attractions": None}))


if __name__ == "__main__":
    unittest.main()
