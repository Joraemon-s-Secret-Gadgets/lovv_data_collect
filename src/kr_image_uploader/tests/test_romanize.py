"""Tests for Korean romanization."""

from __future__ import annotations

import unittest

from kr_image_uploader.romanize import romanize


class RomanizeTest(unittest.TestCase):
    def test_basic_syllables(self) -> None:
        self.assertEqual("Goseokjeong", romanize("고석정"))
        self.assertEqual("Jiktangpokpo", romanize("직탕폭포"))

    def test_rieul_liaison_before_silent_initial(self) -> None:
        # 철원 -> Cheorwon (final rieul + vowel becomes "r", not "l")
        self.assertEqual("Cheorwon", romanize("철원"))

    def test_drops_parenthetical(self) -> None:
        self.assertEqual("Goseokjeong", romanize("고석정 (한탄강 유네스코 세계지질공원)"))
        self.assertEqual("Dopiansa", romanize("도피안사(철원)"))

    def test_keeps_latin_and_digits(self) -> None:
        self.assertEqual("DMZDurumiPyeonghwataun", romanize("DMZ 두루미 평화타운(구 철새마을)"))
        self.assertEqual("Je2ttanggul", romanize("제2땅굴(철원)"))

    def test_empty_or_symbol_only(self) -> None:
        self.assertEqual("", romanize(""))
        self.assertEqual("", romanize("()"))


if __name__ == "__main__":
    unittest.main()
