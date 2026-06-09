"""Tests for S3 raw ingest service."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import tempfile
import unittest

from kr_details_pipeline.raw_ingest import RawIngestConfig, ingest_raw_details


class FakeS3Client:
    def __init__(self, existing_checksum: str | None = None, fail_put: bool = False) -> None:
        self.existing_checksum = existing_checksum
        self.fail_put = fail_put
        self.put_calls: list[dict[str, Any]] = []
        self.head_calls: list[tuple[str, str]] = []

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        self.head_calls.append((Bucket, Key))
        if self.existing_checksum is None:
            raise KeyError("missing")
        return {"Metadata": {"source_checksum_sha256": self.existing_checksum}}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail_put:
            raise RuntimeError("put failed")
        self.put_calls.append(kwargs)
        return {"ETag": "fake"}


class RawIngestTest(unittest.TestCase):
    def test_ingest_uploads_json_and_writes_results(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "details"
            output_dir = root / "ingest"
            input_dir.mkdir()
            _write_city(input_dir / "Wonju.json", "WONJU")

            client = FakeS3Client()
            results = ingest_raw_details(
                RawIngestConfig(
                    input_dir=input_dir,
                    output_dir=output_dir,
                    bucket="bucket",
                    ingest_date="20260609",
                ),
                client,
            )

            self.assertEqual("uploaded", results[0].status)
            self.assertEqual(1, len(client.put_calls))
            self.assertEqual("raw/KR/details/20260609/WONJU.json", client.put_calls[0]["Key"])
            self.assertEqual("application/json", client.put_calls[0]["ContentType"])
            self.assertEqual("WONJU", client.put_calls[0]["Metadata"]["city_name_en"])
            self.assertTrue((output_dir / "raw_manifest.json").exists())
            self.assertTrue((output_dir / "upload_results.jsonl").exists())
            self.assertEqual("", (output_dir / "failed_uploads.jsonl").read_text(encoding="utf-8"))

    def test_ingest_skips_when_remote_checksum_matches(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "details"
            output_dir = root / "ingest"
            input_dir.mkdir()
            _write_city(input_dir / "Wonju.json", "WONJU")

            first_client = FakeS3Client()
            first_results = ingest_raw_details(
                RawIngestConfig(input_dir=input_dir, output_dir=output_dir, bucket="bucket", ingest_date="20260609"),
                first_client,
            )
            checksum = first_results[0].checksum_sha256
            second_client = FakeS3Client(existing_checksum=checksum)
            second_results = ingest_raw_details(
                RawIngestConfig(input_dir=input_dir, output_dir=output_dir, bucket="bucket", ingest_date="20260609"),
                second_client,
            )

            self.assertEqual("skipped", second_results[0].status)
            self.assertEqual(0, len(second_client.put_calls))

    def test_ingest_records_failed_uploads(self) -> None:
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "details"
            output_dir = root / "ingest"
            input_dir.mkdir()
            _write_city(input_dir / "Wonju.json", "WONJU")

            results = ingest_raw_details(
                RawIngestConfig(input_dir=input_dir, output_dir=output_dir, bucket="bucket", ingest_date="20260609"),
                FakeS3Client(fail_put=True),
            )

            self.assertEqual("failed", results[0].status)
            failed_rows = (output_dir / "failed_uploads.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(failed_rows))


def _write_city(path: Path, city_name_en: str) -> None:
    path.write_text(
        json.dumps(
            {
                "meta": {
                    "city_name_en": city_name_en,
                    "city_name_ko": "원주시",
                    "province": "강원특별자치도",
                },
                "attractions": [],
                "festivals": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
