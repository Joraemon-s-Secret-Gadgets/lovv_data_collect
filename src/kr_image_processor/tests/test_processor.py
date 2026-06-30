"""Unit tests for kr_image_processor.processor — city-level image processing."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kr_image_processor.processor import (
    _build_filename,
    _download_with_retry,
    _get_extension_from_url,
    _is_empty_url,
    process_city,
    rewrite_image_urls_to_s3,
)


# ---------------------------------------------------------------------------
# Helper: mock S3 client
# ---------------------------------------------------------------------------

def _make_s3_client(city_data: dict[str, Any]) -> MagicMock:
    """Create a mock S3 client that returns city_data on get_object."""
    client = MagicMock()
    body_bytes = json.dumps(city_data).encode("utf-8")
    body_mock = MagicMock()
    body_mock.read.return_value = body_bytes
    client.get_object.return_value = {"Body": body_mock}
    return client


def _make_image_s3_client() -> MagicMock:
    """Create a mock S3 client for image uploads."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests for _is_empty_url
# ---------------------------------------------------------------------------

class TestIsEmptyUrl:
    def test_none(self):
        assert _is_empty_url(None) is True

    def test_empty_string(self):
        assert _is_empty_url("") is True

    def test_whitespace_only(self):
        assert _is_empty_url("   ") is True

    def test_valid_url(self):
        assert _is_empty_url("http://example.com/img.jpg") is False

    def test_non_string(self):
        assert _is_empty_url(123) is True


# ---------------------------------------------------------------------------
# Tests for _get_extension_from_url
# ---------------------------------------------------------------------------

class TestGetExtensionFromUrl:
    def test_jpg(self):
        assert _get_extension_from_url("http://cdn.example.com/photo.jpg") == "jpg"

    def test_png(self):
        assert _get_extension_from_url("http://cdn.example.com/photo.PNG") == "png"

    def test_with_query_params(self):
        assert _get_extension_from_url("http://cdn.example.com/photo.jpeg?w=400") == "jpeg"

    def test_no_extension(self):
        assert _get_extension_from_url("http://cdn.example.com/photo") == "jpg"

    def test_unknown_extension(self):
        assert _get_extension_from_url("http://cdn.example.com/file.pdf") == "jpg"


# ---------------------------------------------------------------------------
# Tests for _build_filename
# ---------------------------------------------------------------------------

class TestBuildFilename:
    def test_korean_title(self):
        record = {"title": "경복궁", "content_id": "12345"}
        used: set[str] = set()
        result = _build_filename(record, used)
        assert result.isascii()
        assert len(result) > 0

    def test_duplicate_disambiguation(self):
        record1 = {"title": "경복궁", "content_id": "111"}
        record2 = {"title": "경복궁", "content_id": "222"}
        used: set[str] = set()
        name1 = _build_filename(record1, used)
        name2 = _build_filename(record2, used)
        assert name1 != name2
        assert "222" in name2

    def test_empty_title_uses_content_id(self):
        record = {"title": "", "content_id": "99999"}
        used: set[str] = set()
        result = _build_filename(record, used)
        assert result == "99999"

    def test_no_title_no_content_id(self):
        record = {"title": "", "content_id": ""}
        used: set[str] = set()
        result = _build_filename(record, used)
        assert result == "item"


# ---------------------------------------------------------------------------
# Tests for _download_with_retry
# ---------------------------------------------------------------------------

class TestDownloadWithRetry:
    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_success_on_first_attempt(self, mock_sleep, mock_fetch):
        mock_fetch.return_value = b"image_data"
        result = _download_with_retry("http://example.com/img.jpg")
        assert result == b"image_data"
        mock_sleep.assert_not_called()

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_success_on_second_attempt(self, mock_sleep, mock_fetch):
        from urllib.error import URLError
        mock_fetch.side_effect = [URLError("timeout"), b"image_data"]
        result = _download_with_retry("http://example.com/img.jpg")
        assert result == b"image_data"
        mock_sleep.assert_called_once_with(1)  # first backoff: 1s

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_all_retries_exhausted(self, mock_sleep, mock_fetch):
        from urllib.error import URLError
        mock_fetch.side_effect = URLError("timeout")
        with pytest.raises(URLError):
            _download_with_retry("http://example.com/img.jpg")
        assert mock_sleep.call_count == 2  # backoff between attempts 0-1 and 1-2

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep, mock_fetch):
        from urllib.error import URLError
        mock_fetch.side_effect = URLError("timeout")
        with pytest.raises(URLError):
            _download_with_retry("http://example.com/img.jpg")
        # Backoff: 1s (2^0), 2s (2^1)
        assert mock_sleep.call_args_list[0][0][0] == 1
        assert mock_sleep.call_args_list[1][0][0] == 2


# ---------------------------------------------------------------------------
# Tests for process_city (integration-level with mocked S3/HTTP)
# ---------------------------------------------------------------------------

class TestProcessCity:
    """Tests for process_city with mocked dependencies."""

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_successful_download_replaces_url(self, mock_sleep, mock_fetch):
        """Records with valid image_url get S3 URL replacement + image_status ok."""
        mock_fetch.return_value = b"\xff\xd8\xff\xe0fake_jpeg"

        city_data = {
            "city_id": "1",
            "city_name_en": "Seoul",
            "records": [
                {
                    "entity_type": "attraction",
                    "entity_id": "A1",
                    "content_id": "100",
                    "title": "경복궁",
                    "image_url": "http://cdn.example.com/gyeongbok.jpg",
                }
            ],
        }

        s3_client = _make_s3_client(city_data)
        image_s3_client = _make_image_s3_client()

        result = process_city(
            s3_client=s3_client,
            image_s3_client=image_s3_client,
            bucket="test-bucket",
            image_bucket="test-images",
            ingest_date="20260625",
            city_name_en="Seoul",
            source_key="processed/KR/details/20260625/passed/Seoul.json",
        )

        assert result["total_records"] == 1
        assert result["images_downloaded"] == 1
        assert result["images_failed"] == 0
        assert result["no_source_image"] == 0
        assert result["review_count"] == 0
        assert result["review_entries"] == []

        # Verify image was uploaded
        image_s3_client.put_object.assert_called_once()
        put_call = image_s3_client.put_object.call_args
        assert put_call.kwargs["Bucket"] == "test-images"
        assert "images/KR/Seoul/" in put_call.kwargs["Key"]

        # Verify output was written
        s3_client.put_object.assert_called_once()
        output_call = s3_client.put_object.call_args
        assert output_call.kwargs["Key"] == "processed/KR/details/20260625/images/Seoul.json"

        # Verify the record in output has S3 URL
        written_body = json.loads(output_call.kwargs["Body"].decode("utf-8"))
        assert written_body[0]["image_url"].startswith("https://test-images.s3.amazonaws.com/images/KR/Seoul/")
        assert written_body[0]["image_status"] == "ok"

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_download_failure_marks_review(self, mock_sleep, mock_fetch):
        """Records with failed downloads get image_status needs_review."""
        from urllib.error import HTTPError
        mock_fetch.side_effect = HTTPError(
            "http://cdn.example.com/img.jpg", 404, "Not Found", {}, None
        )

        city_data = {
            "city_id": "1",
            "city_name_en": "Seoul",
            "records": [
                {
                    "entity_type": "attraction",
                    "entity_id": "A1",
                    "content_id": "200",
                    "title": "남산타워",
                    "image_url": "http://cdn.example.com/namsan.jpg",
                }
            ],
        }

        s3_client = _make_s3_client(city_data)
        image_s3_client = _make_image_s3_client()

        result = process_city(
            s3_client=s3_client,
            image_s3_client=image_s3_client,
            bucket="test-bucket",
            image_bucket="test-images",
            ingest_date="20260625",
            city_name_en="Seoul",
            source_key="processed/KR/details/20260625/passed/Seoul.json",
        )

        assert result["images_downloaded"] == 0
        assert result["images_failed"] == 1
        assert result["review_count"] == 1
        assert result["review_entries"][0]["failure_reason"] == "download_failed"
        assert result["review_entries"][0]["city_name_en"] == "Seoul"
        assert result["review_entries"][0]["content_id"] == "200"

        # No image upload should happen
        image_s3_client.put_object.assert_not_called()

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_empty_image_url_no_source_image(self, mock_sleep, mock_fetch):
        """Records with null/empty image_url get no_source_image review entry."""
        city_data = {
            "city_id": "1",
            "city_name_en": "Cheorwon",
            "records": [
                {
                    "entity_type": "attraction",
                    "entity_id": "A2",
                    "content_id": "300",
                    "title": "고석정",
                    "image_url": None,
                },
                {
                    "entity_type": "festival",
                    "entity_id": "F1",
                    "content_id": "301",
                    "title": "축제",
                    "image_url": "",
                },
                {
                    "entity_type": "attraction",
                    "entity_id": "A3",
                    "content_id": "302",
                    "title": "빈칸",
                    "image_url": "   ",
                },
            ],
        }

        s3_client = _make_s3_client(city_data)
        image_s3_client = _make_image_s3_client()

        result = process_city(
            s3_client=s3_client,
            image_s3_client=image_s3_client,
            bucket="test-bucket",
            image_bucket="test-images",
            ingest_date="20260625",
            city_name_en="Cheorwon",
            source_key="processed/KR/details/20260625/passed/Cheorwon.json",
        )

        assert result["total_records"] == 3
        assert result["no_source_image"] == 3
        assert result["review_count"] == 3
        for entry in result["review_entries"]:
            assert entry["failure_reason"] == "no_source_image"
            assert entry["city_name_en"] == "Cheorwon"

        # fetch_bytes should never be called for empty URLs
        mock_fetch.assert_not_called()

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_mixed_records(self, mock_sleep, mock_fetch):
        """Mix of successful, failed, and no-image records processed correctly."""
        def side_effect(url, timeout=30):
            if "good" in url:
                return b"image_data"
            from urllib.error import URLError
            raise URLError("Connection refused")

        mock_fetch.side_effect = side_effect

        city_data = {
            "city_id": "1",
            "city_name_en": "Busan",
            "records": [
                {"entity_type": "attraction", "entity_id": "A1", "content_id": "1",
                 "title": "해운대", "image_url": "http://cdn.example.com/good.jpg"},
                {"entity_type": "attraction", "entity_id": "A2", "content_id": "2",
                 "title": "광안리", "image_url": "http://cdn.example.com/bad.jpg"},
                {"entity_type": "festival", "entity_id": "F1", "content_id": "3",
                 "title": "축제", "image_url": None},
            ],
        }

        s3_client = _make_s3_client(city_data)
        image_s3_client = _make_image_s3_client()

        result = process_city(
            s3_client=s3_client,
            image_s3_client=image_s3_client,
            bucket="test-bucket",
            image_bucket="test-images",
            ingest_date="20260625",
            city_name_en="Busan",
            source_key="processed/KR/details/20260625/passed/Busan.json",
        )

        assert result["total_records"] == 3
        assert result["images_downloaded"] == 1
        assert result["images_failed"] == 1
        assert result["no_source_image"] == 1
        assert result["review_count"] == 2  # failed + no_source_image

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_output_key_format(self, mock_sleep, mock_fetch):
        """Output S3 key follows correct pattern."""
        mock_fetch.return_value = b"img"

        city_data = {
            "city_id": "1",
            "city_name_en": "Gangneung",
            "records": [
                {"entity_type": "attraction", "entity_id": "A1", "content_id": "1",
                 "title": "정동진", "image_url": "http://example.com/img.jpg"},
            ],
        }

        s3_client = _make_s3_client(city_data)
        image_s3_client = _make_image_s3_client()

        process_city(
            s3_client=s3_client,
            image_s3_client=image_s3_client,
            bucket="my-bucket",
            image_bucket="img-bucket",
            ingest_date="20260701",
            city_name_en="Gangneung",
            source_key="processed/KR/details/20260701/passed/Gangneung.json",
        )

        output_call = s3_client.put_object.call_args
        assert output_call.kwargs["Key"] == "processed/KR/details/20260701/images/Gangneung.json"

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_record_count_invariant(self, mock_sleep, mock_fetch):
        """Sum of ok + review records equals total input records."""
        mock_fetch.return_value = b"img"

        city_data = {
            "city_id": "1",
            "city_name_en": "Suwon",
            "records": [
                {"entity_type": "attraction", "entity_id": "A1", "content_id": str(i),
                 "title": f"Place{i}", "image_url": f"http://example.com/{i}.jpg"}
                for i in range(5)
            ],
        }

        s3_client = _make_s3_client(city_data)
        image_s3_client = _make_image_s3_client()

        result = process_city(
            s3_client=s3_client,
            image_s3_client=image_s3_client,
            bucket="test-bucket",
            image_bucket="test-images",
            ingest_date="20260625",
            city_name_en="Suwon",
            source_key="processed/KR/details/20260625/passed/Suwon.json",
        )

        total = result["total_records"]
        processed = result["images_downloaded"] + result["images_failed"] + result["no_source_image"]
        assert processed == total

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_review_entry_fields_complete(self, mock_sleep, mock_fetch):
        """Review entries have all required fields."""
        city_data = {
            "city_id": "1",
            "city_name_en": "Daegu",
            "records": [
                {"entity_type": "festival", "entity_id": "F1", "content_id": "500",
                 "title": "꽃축제", "image_url": None},
            ],
        }

        s3_client = _make_s3_client(city_data)
        image_s3_client = _make_image_s3_client()

        result = process_city(
            s3_client=s3_client,
            image_s3_client=image_s3_client,
            bucket="test-bucket",
            image_bucket="test-images",
            ingest_date="20260625",
            city_name_en="Daegu",
            source_key="processed/KR/details/20260625/passed/Daegu.json",
        )

        entry = result["review_entries"][0]
        required_fields = {
            "city_name_en", "content_id", "entity_type",
            "original_image_url", "failure_reason", "error_message", "timestamp",
        }
        assert required_fields.issubset(set(entry.keys()))
        assert entry["city_name_en"] == "Daegu"
        assert entry["content_id"] == "500"
        assert entry["entity_type"] == "festival"
        assert entry["failure_reason"] == "no_source_image"


class TestRewriteImageUrlsToS3:
    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_rewrites_domain_record_and_preserves_source_url(self, mock_sleep, mock_fetch):
        mock_fetch.return_value = b"image"
        image_s3_client = _make_image_s3_client()

        result = rewrite_image_urls_to_s3(
            records=[
                {
                    "entity_type": "attraction",
                    "content_id": "100",
                    "title": "하회마을",
                    "image_url": "https://cdn.example.com/hahoe.webp?size=large",
                },
                {
                    "entity_type": "city_metadata",
                    "city_name_en": "Andong",
                },
            ],
            image_s3_client=image_s3_client,
            image_bucket="image-bucket",
            city_name_en="Andong",
        )

        assert result["images_downloaded"] == 1
        assert result["images_failed"] == 0
        assert result["no_source_image"] == 0

        attraction = result["records"][0]
        city = result["records"][1]
        assert attraction["source_image_url"] == "https://cdn.example.com/hahoe.webp?size=large"
        assert attraction["image_url"].startswith("https://image-bucket.s3.amazonaws.com/images/KR/Andong/")
        assert attraction["image_s3_key"].endswith(".webp")
        assert attraction["image_status"] == "ok"
        assert city == {"entity_type": "city_metadata", "city_name_en": "Andong"}

        image_s3_client.put_object.assert_called_once()
        assert image_s3_client.put_object.call_args.kwargs["Body"] == b"image"

    @patch("kr_image_processor.processor.fetch_bytes")
    @patch("kr_image_processor.processor.time.sleep")
    def test_rejects_non_http_image_url(self, mock_sleep, mock_fetch):
        image_s3_client = _make_image_s3_client()

        result = rewrite_image_urls_to_s3(
            records=[
                {
                    "entity_type": "attraction",
                    "content_id": "101",
                    "title": "하회마을",
                    "image_url": "file:///tmp/private.jpg",
                }
            ],
            image_s3_client=image_s3_client,
            image_bucket="image-bucket",
            city_name_en="Andong",
        )

        assert result["images_downloaded"] == 0
        assert result["images_failed"] == 1
        assert result["review_entries"][0]["failure_reason"] == "unsupported_url_scheme"
        assert result["records"][0]["image_url"] == ""
        assert result["records"][0]["source_image_url"] == "file:///tmp/private.jpg"
        assert result["records"][0]["image_status"] == "needs_review"
        mock_fetch.assert_not_called()
        image_s3_client.put_object.assert_not_called()
