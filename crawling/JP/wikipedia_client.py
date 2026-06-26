"""
일본 도시 취득용 Wikipedia 클라이언트.

이 파일은 Wikipedia HTML 페이지와 선택적 MediaWiki API 대체 경로를 위한
HTTP 접근 및 페이지 추출 도우미를 처리한다.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Final, Protocol

import requests
from bs4 import BeautifulSoup

from crawling.JP.title_filters import is_non_page_title


WIKIPEDIA_API: Final[str] = "https://{lang}.wikipedia.org/w/api.php"
WIKIPEDIA_PAGE: Final[str] = "https://{lang}.wikipedia.org/wiki/{title}"
DEFAULT_USER_AGENT: Final[str] = "LovvCityAcquisition/0.1"


class WikipediaClient(Protocol):
    def fetch_page(self, lang: str, title: str) -> dict[str, Any]:
        ...


class MediaWikiRetryStateError(RuntimeError):
    pass


class MediaWikiClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = 20,
        request_delay_seconds: float = 0.1,
        max_retries: int = 3,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries

    def fetch_page(self, lang: str, title: str) -> dict[str, Any]:
        pages = self.fetch_pages(lang, [title])
        return pages.get(title, {"query": {"pages": []}})

    def fetch_pages(self, lang: str, titles: list[str]) -> dict[str, dict[str, Any]]:
        pages_by_title: dict[str, dict[str, Any]] = {}
        for batch in _chunks(titles, 50):
            payload = self._fetch_pages_batch(lang, batch)
            pages = payload.get("query", {}).get("pages", []) or []
            redirects = payload.get("query", {}).get("redirects", []) or []
            redirect_map = {str(item.get("from")): str(item.get("to")) for item in redirects if item.get("from")}
            response_pages = {str(page.get("title")): page for page in pages}
            for title in batch:
                resolved_title = redirect_map.get(title, title)
                page = response_pages.get(resolved_title) or response_pages.get(title)
                if page is not None:
                    pages_by_title[title] = {"query": {"pages": [page]}}
        return pages_by_title

    def _fetch_pages_batch(self, lang: str, titles: list[str]) -> dict[str, Any]:
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "titles": "|".join(titles),
            "prop": "extracts|coordinates|pageprops|extlinks|langlinks|categories|revisions",
            "rvprop": "content",
            "rvslots": "main",
            "exintro": "1",
            "explaintext": "1",
            "ellimit": "max",
            "lllimit": "max",
            "cllimit": "max",
        }
        url = f"{WIKIPEDIA_API.format(lang=lang)}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        for attempt in range(self.max_retries + 1):
            if self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt >= self.max_retries:
                    raise
                retry_after = error.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after and retry_after.isdigit() else 10.0
                time.sleep(wait_seconds)
        raise MediaWikiRetryStateError


class WikipediaHtmlClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = 20,
        request_delay_seconds: float = 0.05,
        session: requests.Session | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.request_delay_seconds = request_delay_seconds
        self.session = session or requests.Session()

    def fetch_page(self, lang: str, title: str) -> dict[str, Any]:
        pages = self.fetch_pages(lang, [title])
        return pages.get(title, {"query": {"pages": []}})

    def fetch_pages(self, lang: str, titles: list[str]) -> dict[str, dict[str, Any]]:
        pages_by_title: dict[str, dict[str, Any]] = {}
        for title in titles:
            if self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)
            html = self._fetch_page_html(lang, title)
            page = parse_wikipedia_html(lang, title, html)
            pages_by_title[title] = {"query": {"pages": [page]}}
        return pages_by_title

    def _fetch_page_html(self, lang: str, title: str) -> str:
        encoded_title = urllib.parse.quote(title.replace(" ", "_"))
        url = WIKIPEDIA_PAGE.format(lang=lang, title=encoded_title)
        response = self.session.get(url, headers={"User-Agent": self.user_agent}, timeout=self.timeout)
        response.raise_for_status()
        return response.text


def parse_wikipedia_html(lang: str, fallback_title: str, html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for noisy in soup.find_all(["style", "script"]):
        noisy.decompose()
    title_node = soup.find("h1", id="firstHeading")
    content_root = soup.find(id="mw-content-text")
    content = (
        content_root.find("div", class_="mw-parser-output")
        if content_root is not None
        else soup.find("div", class_="mw-parser-output")
    )
    lead_paragraphs: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    if content is not None:
        if content.find("section"):
            lead_paragraphs, sections = _extract_parsoid_sections(content)
        else:
            lead_paragraphs, sections = _extract_legacy_sections(content)
    coordinates: list[dict[str, float]] = []
    geo_node = content.find(class_="geo-dec") if content is not None else soup.find(class_="geo-dec")
    if geo_node is not None:
        parsed_coordinates = _parse_geo_decimal(geo_node.get_text(""))
        if parsed_coordinates:
            coordinates.append({"lat": parsed_coordinates[0], "lon": parsed_coordinates[1]})
    extlinks = _external_links(soup)
    langlinks = _language_links(soup)
    return {
        "title": _clean_html_text(title_node.get_text("") if title_node else "") or fallback_title,
        "extract": "\n\n".join(lead_paragraphs),
        "coordinates": coordinates,
        "extlinks": extlinks,
        "langlinks": langlinks,
        "revisions": [{"slots": {"main": {"content": _synthetic_revision_content(sections)}}}],
    }


def _clean_html_text(text: str) -> str:
    return " ".join(text.split())


def _extract_legacy_sections(content: BeautifulSoup) -> tuple[list[str], list[tuple[str, list[str]]]]:
    lead_paragraphs: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_section: tuple[str, list[str]] | None = None
    for node in content.find_all(["p", "h2", "h3"], recursive=False):
        if node.name in {"h2", "h3"}:
            headline = node.find(class_="mw-headline")
            heading = _clean_html_text((headline or node).get_text(""))
            if heading:
                current_section = (heading, [])
                sections.append(current_section)
            continue
        text = _clean_html_text(node.get_text(""))
        if not text:
            continue
        if current_section is None:
            lead_paragraphs.append(text)
        else:
            current_section[1].append(text)
    return lead_paragraphs, sections


def _extract_parsoid_sections(content: BeautifulSoup) -> tuple[list[str], list[tuple[str, list[str]]]]:
    lead_paragraphs: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for section in content.find_all("section"):
        section_id = str(section.get("data-mw-section-id") or "")
        paragraphs = [_clean_html_text(paragraph.get_text("")) for paragraph in section.find_all("p", recursive=False)]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]
        if section_id == "0":
            lead_paragraphs.extend(paragraphs)
            continue
        heading_node = section.find(["h2", "h3"], recursive=False)
        if heading_node is None:
            heading_container = section.find("div", class_=re.compile(r"\bmw-heading\b"), recursive=False)
            if heading_container is not None:
                heading_node = heading_container.find(["h2", "h3"], recursive=False)
        heading = _clean_html_text(heading_node.get_text("") if heading_node else str(section.get("aria-labelledby") or ""))
        if heading and paragraphs:
            sections.append((heading, paragraphs))
    return lead_paragraphs, sections


def _parse_geo_decimal(text: str) -> tuple[float, float] | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(numbers) < 2:
        return None
    return float(numbers[0]), float(numbers[1])


def _title_from_wiki_href(href: str) -> str:
    path = urllib.parse.urlparse(href).path
    if "/wiki/" not in path:
        return ""
    return urllib.parse.unquote(path.rsplit("/wiki/", 1)[1]).replace("_", " ")


def _external_links(soup: BeautifulSoup) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        seen.add(href)
        links.append({"url": href})
    return links


def _language_links(soup: BeautifulSoup) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    language_anchors = soup.select("li.interlanguage-link a[href][hreflang]")
    if not language_anchors:
        language_anchors = soup.find_all("a", href=True, hreflang=True)
    for anchor in language_anchors:
        lang = str(anchor["hreflang"])
        title = _title_from_wiki_href(str(anchor["href"]))
        if is_non_page_title(title):
            continue
        item = {"lang": lang, "title": title}
        if title and item not in links:
            links.append(item)
    return links


def _synthetic_revision_content(sections: list[tuple[str, list[str]]]) -> str:
    parts: list[str] = []
    for heading, paragraphs in sections:
        if not paragraphs:
            continue
        parts.append(f"== {heading} ==\n" + "\n\n".join(paragraphs))
    return "\n\n".join(parts)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def first_page(payload: dict[str, Any]) -> dict[str, Any]:
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        return {}
    page = pages[0]
    if page.get("missing"):
        return {}
    return page


# 파일 이력
# 2026-06-04: CLI 모듈에서 Wikipedia 접근을 분리했다.
