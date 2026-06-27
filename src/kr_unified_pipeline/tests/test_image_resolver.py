"""
Unit tests for the ImageResolver module.

Tests cover:
- Wikipedia pageimages API integration (mocked HTTP)
- TourAPI firstimage extraction
- URL validation
- apply_to_record hierarchy (Wikipedia=primary, TourAPI=secondary)
- Graceful handling of null/empty inputs
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kr_unified_pipeline.image_resolver import ImageResolver, _is_valid_url
from kr_unified_pipeline.models import CityRecord, ImageSource


# ---------------------------------------------------------------------------
# URL Validation Tests
# ---------------------------------------------------------------------------


class TestUrlValidation:
    """Tests for the _is_valid_url helper function."""

    def test_valid_https_url(self) -> None:
        assert _is_valid_url("https://upload.wikimedia.org/image.jpg") is True

    def test_valid_http_url(self) -> None:
        assert _is_valid_url("http://example.com/photo.png") is True

    def test_none_returns_false(self) -> None:
        assert _is_valid_url(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert _is_valid_url("") is False

    def test_whitespace_only_returns_false(self) -> None:
        assert _is_valid_url("   ") is False

    def test_ftp_url_returns_false(self) -> None:
        assert _is_valid_url("ftp://example.com/file.jpg") is False

    def test_relative_path_returns_false(self) -> None:
        assert _is_valid_url("/images/photo.jpg") is False

    def test_no_protocol_returns_false(self) -> None:
        assert _is_valid_url("example.com/image.jpg") is False

    def test_valid_url_with_query_params(self) -> None:
        assert _is_valid_url("https://example.com/img?width=300&format=jpg") is True

    def test_valid_url_with_korean_encoded(self) -> None:
        assert _is_valid_url("https://ko.wikipedia.org/wiki/%EC%84%9C%EC%9A%B8") is True


# ---------------------------------------------------------------------------
# resolve_wikipedia_image Tests
# ---------------------------------------------------------------------------


class TestResolveWikipediaImage:
    """Tests for Wikipedia pageimages API integration."""

    def setup_method(self) -> None:
        self.resolver = ImageResolver(timeout=5)

    def test_returns_thumbnail_url_on_success(self) -> None:
        """Should return the thumbnail source URL when available."""
        mock_session = MagicMock()
        self.resolver.session = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {
                "pages": [
                    {
                        "pageid": 12345,
                        "title": "서울특별시",
                        "thumbnail": {
                            "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Seoul.jpg/300px-Seoul.jpg",
                            "width": 300,
                            "height": 200,
                        },
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        result = self.resolver.resolve_wikipedia_image("서울특별시", lang="ko")
        assert result == "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Seoul.jpg/300px-Seoul.jpg"

    def test_returns_none_for_empty_title(self) -> None:
        """Should return None for empty page title without making API call."""
        result = self.resolver.resolve_wikipedia_image("")
        assert result is None

    def test_returns_none_for_whitespace_title(self) -> None:
        """Should return None for whitespace-only page title."""
        result = self.resolver.resolve_wikipedia_image("   ")
        assert result is None

    def test_returns_none_when_page_missing(self) -> None:
        """Should return None when Wikipedia page does not exist."""
        mock_session = MagicMock()
        self.resolver.session = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {
                "pages": [{"title": "NonExistent", "missing": True}]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        result = self.resolver.resolve_wikipedia_image("NonExistent")
        assert result is None

    def test_returns_none_when_no_thumbnail(self) -> None:
        """Should return None when page exists but has no thumbnail."""
        mock_session = MagicMock()
        self.resolver.session = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {"pages": [{"pageid": 999, "title": "SomePage"}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        result = self.resolver.resolve_wikipedia_image("SomePage")
        assert result is None

    def test_returns_none_on_network_error(self) -> None:
        """Should return None and log warning on network error."""
        mock_session = MagicMock()
        self.resolver.session = mock_session

        import requests as req

        mock_session.get.side_effect = req.ConnectionError("Network unreachable")

        result = self.resolver.resolve_wikipedia_image("서울특별시")
        assert result is None

    def test_passes_correct_api_params(self) -> None:
        """Should pass correct params including pithumbsize=300 and redirects=1."""
        mock_session = MagicMock()
        self.resolver.session = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {"query": {"pages": []}}
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        self.resolver.resolve_wikipedia_image("부산광역시", lang="ko")

        call_args = mock_session.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params")
        assert params["pithumbsize"] == "300"
        assert params["redirects"] == "1"
        assert params["prop"] == "pageimages"
        assert params["piprop"] == "thumbnail"
        assert "ko.wikipedia.org" in call_args.args[0]


# ---------------------------------------------------------------------------
# resolve_tourapi_image Tests
# ---------------------------------------------------------------------------


class TestResolveTourApiImage:
    """Tests for TourAPI firstimage extraction."""

    def setup_method(self) -> None:
        self.resolver = ImageResolver()

    def test_extracts_valid_firstimage(self) -> None:
        """Should extract firstimage URL when present and valid."""
        detail = {"firstimage": "https://tong.visitkorea.or.kr/cms/resource/01/image.jpg"}
        result = self.resolver.resolve_tourapi_image(detail)
        assert result == "https://tong.visitkorea.or.kr/cms/resource/01/image.jpg"

    def test_returns_none_for_empty_firstimage(self) -> None:
        """Should return None for empty firstimage (Requirement 6.4)."""
        detail = {"firstimage": ""}
        result = self.resolver.resolve_tourapi_image(detail)
        assert result is None

    def test_returns_none_for_null_firstimage(self) -> None:
        """Should return None for null firstimage (Requirement 6.4)."""
        detail = {"firstimage": None}
        result = self.resolver.resolve_tourapi_image(detail)
        assert result is None

    def test_returns_none_for_missing_firstimage_key(self) -> None:
        """Should return None when firstimage key is absent."""
        detail = {"title": "Some Place", "addr1": "Seoul"}
        result = self.resolver.resolve_tourapi_image(detail)
        assert result is None

    def test_returns_none_for_empty_dict(self) -> None:
        """Should return None for empty detail dictionary."""
        result = self.resolver.resolve_tourapi_image({})
        assert result is None

    def test_returns_none_for_none_input(self) -> None:
        """Should return None for None input."""
        result = self.resolver.resolve_tourapi_image(None)  # type: ignore[arg-type]
        assert result is None

    def test_returns_none_for_invalid_url_format(self) -> None:
        """Should reject firstimage with invalid URL format (Requirement 6.5)."""
        detail = {"firstimage": "not-a-valid-url"}
        result = self.resolver.resolve_tourapi_image(detail)
        assert result is None

    def test_strips_whitespace_from_firstimage(self) -> None:
        """Should strip whitespace from firstimage URL."""
        detail = {"firstimage": "  https://example.com/img.jpg  "}
        result = self.resolver.resolve_tourapi_image(detail)
        assert result == "https://example.com/img.jpg"

    def test_returns_none_for_whitespace_only_firstimage(self) -> None:
        """Should return None for whitespace-only firstimage."""
        detail = {"firstimage": "   "}
        result = self.resolver.resolve_tourapi_image(detail)
        assert result is None


# ---------------------------------------------------------------------------
# apply_to_record Tests
# ---------------------------------------------------------------------------


class TestApplyToRecord:
    """Tests for the apply_to_record hierarchy logic."""

    def setup_method(self) -> None:
        self.resolver = ImageResolver()

    def test_wikipedia_sets_primary_image(self) -> None:
        """Wikipedia source should set image_url as primary (Requirement 5.2)."""
        record = CityRecord(city_id="seoul")
        self.resolver.apply_to_record(
            record, "wikipedia", "https://upload.wikimedia.org/img.jpg"
        )
        assert record.image_url == "https://upload.wikimedia.org/img.jpg"
        assert len(record.image_urls) == 1
        assert record.image_urls[0].source == "wikipedia"

    def test_tourapi_sets_primary_when_no_existing(self) -> None:
        """TourAPI should become primary when no image_url exists (Requirement 6.3)."""
        record = CityRecord(city_id="busan")
        self.resolver.apply_to_record(
            record, "tourapi", "https://tong.visitkorea.or.kr/img.jpg"
        )
        assert record.image_url == "https://tong.visitkorea.or.kr/img.jpg"
        assert len(record.image_urls) == 1
        assert record.image_urls[0].source == "tourapi"

    def test_tourapi_secondary_when_wikipedia_exists(self) -> None:
        """TourAPI should be secondary when Wikipedia image already set (Requirement 6.2)."""
        record = CityRecord(
            city_id="seoul",
            image_url="https://upload.wikimedia.org/wiki.jpg",
            image_urls=[ImageSource(url="https://upload.wikimedia.org/wiki.jpg", source="wikipedia")],
        )
        self.resolver.apply_to_record(
            record, "tourapi", "https://tong.visitkorea.or.kr/tour.jpg"
        )
        # Primary should remain Wikipedia
        assert record.image_url == "https://upload.wikimedia.org/wiki.jpg"
        # TourAPI should be added to image_urls
        assert len(record.image_urls) == 2
        assert record.image_urls[1].url == "https://tong.visitkorea.or.kr/tour.jpg"
        assert record.image_urls[1].source == "tourapi"

    def test_wikipedia_overwrites_tourapi_primary(self) -> None:
        """Wikipedia should overwrite existing TourAPI primary (Wikipedia always primary)."""
        record = CityRecord(
            city_id="incheon",
            image_url="https://tong.visitkorea.or.kr/old.jpg",
            image_urls=[ImageSource(url="https://tong.visitkorea.or.kr/old.jpg", source="tourapi")],
        )
        self.resolver.apply_to_record(
            record, "wikipedia", "https://upload.wikimedia.org/new.jpg"
        )
        assert record.image_url == "https://upload.wikimedia.org/new.jpg"
        assert len(record.image_urls) == 2

    def test_invalid_url_is_noop(self) -> None:
        """Should not modify record when URL is invalid (Requirement 6.5)."""
        record = CityRecord(city_id="test")
        self.resolver.apply_to_record(record, "wikipedia", "not-a-url")
        assert record.image_url is None
        assert record.image_urls == []

    def test_empty_url_is_noop(self) -> None:
        """Should not modify record when URL is empty."""
        record = CityRecord(city_id="test")
        self.resolver.apply_to_record(record, "tourapi", "")
        assert record.image_url is None
        assert record.image_urls == []

    def test_no_duplicate_urls_in_image_urls(self) -> None:
        """Should not add duplicate URLs to image_urls list."""
        record = CityRecord(city_id="daegu")
        url = "https://upload.wikimedia.org/img.jpg"
        self.resolver.apply_to_record(record, "wikipedia", url)
        self.resolver.apply_to_record(record, "wikipedia", url)
        assert len(record.image_urls) == 1
