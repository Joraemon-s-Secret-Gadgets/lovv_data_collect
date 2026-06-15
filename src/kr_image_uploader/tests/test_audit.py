"""Tests for the upload audit/reconciliation logic (no network, no AWS)."""

from __future__ import annotations

import unittest

from kr_image_uploader import download
from kr_image_uploader.audit import expected_files, find_missing, recover_missing

_PAYLOAD = {
    "attractions": [
        {
            "contentid": "1",
            "title": "고석정",
            "firstimage": "http://x/a_2.jpg",
            "firstimage2": "http://x/a_3.png",
        },
        {
            "contentid": "2",
            "title": "도피안사",
            "firstimage": "http://x/b_2.JPG",
            "firstimage2": "",
        },
    ]
}


class AuditTest(unittest.TestCase):
    def test_expected_files_uses_image_keys(self) -> None:
        expected = expected_files(_PAYLOAD, "Cheorwon")
        self.assertEqual(
            {"Goseokjeong_1.jpg", "Goseokjeong_2.png", "Dopiansa_1.jpg"},
            set(expected),
        )

    def test_find_missing_reports_absent_files(self) -> None:
        expected = expected_files(_PAYLOAD, "Cheorwon")
        # only two of the three were actually uploaded
        actual = {"Goseokjeong_1.jpg", "Goseokjeong_2.png"}
        missing = find_missing(expected, actual)
        self.assertEqual({"Dopiansa_1.jpg"}, set(missing))
        self.assertEqual("http://x/b_2.JPG", missing["Dopiansa_1.jpg"].url)

    def test_find_missing_empty_when_all_present(self) -> None:
        expected = expected_files(_PAYLOAD, "Cheorwon")
        self.assertEqual({}, find_missing(expected, set(expected)))


class _FakeS3:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_object(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return {}


class RecoverMissingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = download.fetch_bytes

    def tearDown(self) -> None:
        download.fetch_bytes = self._orig  # type: ignore[assignment]

    def test_only_downloadable_missing_are_uploaded(self) -> None:
        expected = expected_files(_PAYLOAD, "Cheorwon")
        # all three are "missing" from S3
        missing = find_missing(expected, set())

        # one URL downloads fine, the rest 404 (dead source)
        good_url = "http://x/a_2.jpg"

        def fake_fetch(url, timeout=30):
            if url == good_url:
                return b"bytes"
            raise OSError("404")

        download.fetch_bytes = fake_fetch  # type: ignore[assignment]

        client = _FakeS3()
        recovered, failed = recover_missing(client, "bucket", "images/KR", "Cheorwon", missing)

        # exactly one object uploaded, to the right key
        self.assertEqual(1, len(client.calls))
        self.assertEqual("images/KR/Cheorwon/Goseokjeong_1.jpg", client.calls[0]["Key"])
        self.assertEqual(["Goseokjeong_1.jpg"], recovered)
        self.assertEqual(2, len(failed))


if __name__ == "__main__":
    unittest.main()
