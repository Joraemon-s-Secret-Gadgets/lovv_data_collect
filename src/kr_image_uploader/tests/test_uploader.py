"""Tests for the upload orchestration (no network, no AWS)."""

from __future__ import annotations

import contextlib
import io
import unittest

from kr_image_uploader import download, uploader


def _run_quiet(*args, **kwargs):
    """Call upload_city while suppressing its stdout logging."""
    with contextlib.redirect_stdout(io.StringIO()):
        return uploader.upload_city(*args, **kwargs)

_PAYLOAD = {
    "attractions": [
        {
            "contentid": "1",
            "title": "고석정",
            "firstimage": "http://x/a_2.jpg",
            "firstimage2": "http://x/a_3.png",
        }
    ]
}


class _FakeS3:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_object(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return {}


class UploaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = download.fetch_bytes
        download.fetch_bytes = lambda url, timeout=30: b"bytes"  # type: ignore[assignment]

    def tearDown(self) -> None:
        download.fetch_bytes = self._orig  # type: ignore[assignment]

    def test_uploads_each_image_with_content_type(self) -> None:
        client = _FakeS3()
        result = _run_quiet(_PAYLOAD, "Cheorwon", "bucket", client)

        self.assertEqual(2, result.uploaded)
        self.assertEqual(0, result.failed)
        keys = sorted(c["Key"] for c in client.calls)
        self.assertEqual(
            ["images/KR/Cheorwon/Goseokjeong_1.jpg",
             "images/KR/Cheorwon/Goseokjeong_2.png"],
            keys,
        )
        ctypes = {c["Key"]: c["ContentType"] for c in client.calls}
        self.assertEqual("image/jpeg", ctypes["images/KR/Cheorwon/Goseokjeong_1.jpg"])
        self.assertEqual("image/png", ctypes["images/KR/Cheorwon/Goseokjeong_2.png"])

    def test_dry_run_does_not_call_client(self) -> None:
        client = _FakeS3()
        _run_quiet(_PAYLOAD, "Cheorwon", "bucket", client, dry_run=True)
        self.assertEqual([], client.calls)

    def test_download_failure_is_counted_not_raised(self) -> None:
        def boom(url, timeout=30):
            raise OSError("dead url")

        download.fetch_bytes = boom  # type: ignore[assignment]
        client = _FakeS3()
        result = _run_quiet(_PAYLOAD, "Cheorwon", "bucket", client)
        self.assertEqual(0, result.uploaded)
        self.assertEqual(2, result.failed)


if __name__ == "__main__":
    unittest.main()
