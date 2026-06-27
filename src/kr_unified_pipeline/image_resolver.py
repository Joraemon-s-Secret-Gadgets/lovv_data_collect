"""
Image URL resolution for the unified preprocessing pipeline.

This module resolves representative image URLs from Wikipedia (pageimages API)
and TourAPI (firstimage field), applies a hierarchical storage strategy
(Wikipedia=primary, TourAPI=secondary), and validates URLs before storing.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import logging
import re
import urllib.parse

import requests

from kr_unified_pipeline.models import CityRecord, ImageSource

logger = logging.getLogger(__name__)

# Minimum thumbnail width in pixels (Requirement 5.4)
_MIN_THUMBNAIL_WIDTH: int = 300

# Wikipedia API base URL template
_WIKIPEDIA_API_URL: str = "https://{lang}.wikipedia.org/w/api.php"

# URL validation pattern: must start with http:// or https:// and have a valid format
_URL_PATTERN: re.Pattern[str] = re.compile(
    r"^https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$"
)


def _is_valid_url(url: str | None) -> bool:
    """Validate that a URL conforms to HTTP/HTTPS format.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL is a valid HTTP or HTTPS URL, False otherwise.
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    return _URL_PATTERN.match(url) is not None


class ImageResolver:
    """Resolves and stores image URLs from Wikipedia and TourAPI sources.

    The resolver fetches Wikipedia page thumbnails via the pageimages API
    and extracts TourAPI firstimage URLs. It applies a hierarchical strategy:
    Wikipedia images are treated as primary, TourAPI images as secondary.

    Attributes:
        session: HTTP session for Wikipedia API requests.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: int = 15,
        user_agent: str = "LovvUnifiedPipeline/0.1",
    ) -> None:
        """Initialize the ImageResolver.

        Args:
            session: Optional requests session for HTTP calls.
            timeout: HTTP request timeout in seconds.
            user_agent: User-Agent header for Wikipedia API requests.
        """
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.setdefault("User-Agent", user_agent)

    def resolve_wikipedia_image(
        self, page_title: str, lang: str = "ko"
    ) -> str | None:
        """Query Wikipedia pageimages API for a page's primary thumbnail URL.

        Requests a thumbnail at minimum width of 300px. Follows redirects
        as specified by the Wikipedia API redirects parameter.

        Args:
            page_title: The Wikipedia page title to look up.
            lang: Wikipedia language edition (default: "ko").

        Returns:
            The thumbnail URL string if available, or None if no image exists
            or an error occurs.

        Requirements: 5.1, 5.4, 5.5
        """
        if not page_title or not page_title.strip():
            return None

        api_url = _WIKIPEDIA_API_URL.format(lang=lang)
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "titles": page_title,
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": str(_MIN_THUMBNAIL_WIDTH),
            "redirects": "1",
        }

        try:
            response = self.session.get(
                api_url, params=params, timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning(
                "Wikipedia pageimages API error for '%s' (lang=%s): %s",
                page_title,
                lang,
                exc,
            )
            return None

        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return None

        page = pages[0]
        # Check if page is missing (no such page exists)
        if page.get("missing", False):
            return None

        thumbnail = page.get("thumbnail", {})
        source_url = thumbnail.get("source")

        if source_url and _is_valid_url(source_url):
            return source_url

        return None

    def resolve_tourapi_image(self, detail_data: dict) -> str | None:
        """Extract the firstimage URL from TourAPI detail response data.

        Handles null, empty, or missing firstimage gracefully without error
        (Requirement 6.4).

        Args:
            detail_data: A dictionary containing TourAPI detail fields.
                         Expected to have a "firstimage" key with a URL value.

        Returns:
            The firstimage URL if present and valid, or None otherwise.

        Requirements: 6.1, 6.4, 6.5
        """
        if not detail_data or not isinstance(detail_data, dict):
            return None

        firstimage = detail_data.get("firstimage")

        # Handle null/empty gracefully (Requirement 6.4)
        if not firstimage or not isinstance(firstimage, str):
            return None

        firstimage = firstimage.strip()
        if not firstimage:
            return None

        # Validate URL format (Requirement 6.5)
        if _is_valid_url(firstimage):
            return firstimage

        return None

    def apply_to_record(
        self, record: CityRecord, source: str, url: str
    ) -> None:
        """Apply an image URL to a CityRecord following the hierarchy rules.

        Hierarchy:
        - Wikipedia images are treated as PRIMARY (set as image_url).
        - TourAPI images are treated as SECONDARY:
          - If no image_url exists, TourAPI becomes primary (Requirement 6.3).
          - If image_url already exists (from Wikipedia), TourAPI is appended
            to image_urls as secondary (Requirement 6.2).

        URL validation is performed before storing (Requirement 6.5).
        The method is a no-op if the URL is invalid.

        Args:
            record: The CityRecord to update.
            source: The source identifier ("wikipedia" or "tourapi").
            url: The image URL to store.

        Requirements: 5.2, 6.2, 6.3, 6.5
        """
        if not _is_valid_url(url):
            return

        image_source = ImageSource(url=url, source=source)

        if source == "wikipedia":
            # Wikipedia is always primary (Requirement 5.2)
            record.image_url = url
            # Add to image_urls list if not already present
            if not any(img.url == url for img in record.image_urls):
                record.image_urls.append(image_source)
        elif source == "tourapi":
            # TourAPI: secondary if Wikipedia already set, otherwise primary
            if record.image_url is None:
                # No existing primary → TourAPI becomes primary (Requirement 6.3)
                record.image_url = url
            # Always add to image_urls list (Requirement 6.2)
            if not any(img.url == url for img in record.image_urls):
                record.image_urls.append(image_source)
        else:
            # Unknown source: still add to image_urls if valid
            if not any(img.url == url for img in record.image_urls):
                record.image_urls.append(image_source)
            if record.image_url is None:
                record.image_url = url
