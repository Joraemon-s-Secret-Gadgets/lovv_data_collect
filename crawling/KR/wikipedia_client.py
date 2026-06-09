"""
Wikipedia clients for South Korea city acquisition.

This file handles HTTP access and page extraction helpers for Wikipedia HTML
pages and the optional MediaWiki API fallback.
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


WIKIPEDIA_API: Final[str] = "https://{lang}.wikipedia.org/w/api.php"
WIKIPEDIA_PAGE: Final[str] = "https://{lang}.wikipedia.org/wiki/{title}"
DEFAULT_USER_AGENT: Final[str] = "LovvCityAcquisition/0.1"


class WikipediaClient(Protocol):
    def fetch_page(self, lang: str, title: str) -> dict[str, Any]:
        ...


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
        raise RuntimeError("Unreachable MediaWiki retry state.")


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
            
    if not coordinates:
        # Fallback: parse coordinates from geohack links in HTML
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"])
            if "geohack" in href:
                coords = _parse_geohack_from_href(href)
                if coords:
                    coordinates.append({"lat": coords[0], "lon": coords[1]})
                    break

    extlinks = _external_links(soup)
    langlinks = _language_links(soup)
    climate_table = _extract_climate_table_from_html(soup)
    return {
        "title": _clean_html_text(title_node.get_text("") if title_node else "") or fallback_title,
        "extract": "\n\n".join(lead_paragraphs),
        "coordinates": coordinates,
        "extlinks": extlinks,
        "langlinks": langlinks,
        "climate_table": climate_table,
        "revisions": [{"slots": {"main": {"content": _synthetic_revision_content(sections)}}}],
    }


def _parse_geohack_from_href(href: str) -> tuple[float, float] | None:
    try:
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        params_list = query.get("params")
        params = params_list[0] if params_list else href
        decimal_match = re.search(r"(-?\d+(?:\.\d+)?)_([NS])_(-?\d+(?:\.\d+)?)_([EW])", params)
        if decimal_match:
            lat = float(decimal_match.group(1))
            lon = float(decimal_match.group(3))
            if decimal_match.group(2) == "S":
                lat *= -1
            if decimal_match.group(4) == "W":
                lon *= -1
            return lat, lon

        match = re.search(
            r"([0-9.]+)_([0-9.]+)?_?([0-9.]+)?_?([NS])_([0-9.]+)_([0-9.]+)?_?([0-9.]+)?_?([EW])",
            params,
        )
        if not match:
            return None

        def to_dec(deg: str, mins: str | None, secs: str | None, direct: str) -> float:
            val = float(deg)
            if mins:
                val += float(mins) / 60
            if secs:
                val += float(secs) / 3600
            if direct in ("S", "W"):
                val *= -1
            return val

        lat = to_dec(match.group(1), match.group(2), match.group(3), match.group(4))
        lon = to_dec(match.group(5), match.group(6), match.group(7), match.group(8))
        return lat, lon
    except Exception:
        return None


def _clean_html_text(text: str) -> str:
    return " ".join(text.split())


def _extract_legacy_sections(content: BeautifulSoup) -> tuple[list[str], list[tuple[str, list[str]]]]:
    lead_paragraphs: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_section: tuple[str, list[str]] | None = None
    for node in content.find_all(["p", "h2"], recursive=False):
        if node.name == "h2":
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
    for section in content.find_all("section", recursive=False):
        section_id = str(section.get("data-mw-section-id") or "")
        paragraphs = [_clean_html_text(paragraph.get_text("")) for paragraph in section.find_all("p")]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]
        if section_id == "0":
            lead_paragraphs.extend(paragraphs)
            continue
        heading_node = section.find("h2")
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
    for anchor in soup.find_all("a", href=True, hreflang=True):
        lang = str(anchor["hreflang"])
        title = _title_from_wiki_href(str(anchor["href"]))
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


def html_table_to_wikitext(table_node: BeautifulSoup) -> str:
    if not table_node:
        return ""
    
    lines = []
    classes = table_node.get("class", [])
    class_attr = f' class="{" ".join(classes)}"' if classes else ''
    lines.append(f"{{|{class_attr}")
    
    caption = table_node.find("caption")
    if caption:
        lines.append(f"|+ {caption.get_text(strip=True)}")
        
    for tr in table_node.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
            
        row_cells = []
        is_header_row = all(cell.name == "th" for cell in cells)
        
        for cell in cells:
            cell_text = cell.get_text(strip=True)
            cell_text = re.sub(r'\[\d+\]', '', cell_text)
            
            attrs = []
            if cell.get("colspan"):
                attrs.append(f'colspan="{cell["colspan"]}"')
            if cell.get("rowspan"):
                attrs.append(f'rowspan="{cell["rowspan"]}"')
                
            attr_str = " ".join(attrs) + " | " if attrs else ""
            row_cells.append(f"{attr_str}{cell_text}")
            
        lines.append("|-")
        if is_header_row:
            lines.append("! " + " !! ".join(row_cells))
        else:
            lines.append("| " + " || ".join(row_cells))
            
    lines.append("|}")
    return "\n".join(lines)


def _extract_climate_table_from_html(soup: BeautifulSoup) -> dict[str, Any] | None:
    tables = soup.find_all("table")
    for table in tables:
        table_text = table.get_text()
        if "월" in table_text and ("기온" in table_text or "강수량" in table_text or "기후" in table_text):
            classes = table.get("class", [])
            if "wikitable" in classes:
                wikitext = html_table_to_wikitext(table)
                caption_node = table.find("caption")
                caption = caption_node.get_text(strip=True) if caption_node else ""
                if not caption:
                    prev = table.find_previous(["h2", "h3"])
                    caption = prev.get_text(strip=True) if prev else "기후"
                caption = re.sub(r'\[\d+\]', '', caption)
                
                structured_data = parse_structured_climate_table(table)
                return {
                    "caption": caption,
                    "wikitext": wikitext,
                    "data": structured_data
                }
    return None


def parse_structured_climate_table(table_node: BeautifulSoup) -> dict[str, dict[str, str]]:
    if not table_node:
        return {}
        
    rows = table_node.find_all("tr")
    month_row_index = -1
    month_columns = {}
    
    for r_idx, tr in enumerate(rows):
        cells = tr.find_all(["th", "td"], recursive=False)
        cell_texts = [c.get_text(strip=True) for c in cells]
        if "1월" in cell_texts and "12월" in cell_texts:
            month_row_index = r_idx
            start_col = -1
            for c_idx, text in enumerate(cell_texts):
                if "1월" in text:
                    start_col = c_idx
                    break
            
            if start_col != -1:
                for c_idx in range(start_col, len(cell_texts)):
                    month_name = cell_texts[c_idx]
                    month_name = re.sub(r'\[\d+\]', '', month_name).strip()
                    month_columns[c_idx] = month_name
            break
            
    if month_row_index == -1 or not month_columns:
        return {}
        
    structured_data = {}
    for month_name in month_columns.values():
        structured_data[month_name] = {}
        
    for r_idx, tr in enumerate(rows):
        if r_idx <= month_row_index:
            continue
            
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
            
        item_label = cells[0].get_text(strip=True)
        item_label = re.sub(r'\[\d+\]', '', item_label)
        
        # Clean item label
        item_label_clean = item_label.replace('\xa0', ' ')
        # Remove unit terms in parentheses
        item_label_clean = re.sub(r'\s*\([^)]*(?:°C|°F|mm|%|일|inch|인치|센티미터|m|ft)[^)]*\)', '', item_label_clean)
        # Remove standalone unit markings
        item_label_clean = re.sub(r'\s*(?:°C|°F|mm|%)\b', '', item_label_clean)
        item_label_clean = item_label_clean.strip()
        
        if len(cells) < len(month_columns):
            continue
            
        for c_idx, month_name in month_columns.items():
            if c_idx < len(cells):
                cell_value = cells[c_idx].get_text(strip=True)
                cell_value = re.sub(r'\[\d+\]', '', cell_value)
                
                # Replace Unicode minus sign with hyphen-minus
                cell_value = cell_value.replace('−', '-').replace('\u2212', '-')
                # Remove commas from large numbers
                cell_value = cell_value.replace(',', '')
                
                # Extract clean float or int
                val_match = re.search(r'(-?\d+(?:\.\d+)?)', cell_value)
                if val_match:
                    clean_value = val_match.group(1)
                else:
                    clean_value = cell_value
                    
                structured_data[month_name][item_label_clean] = clean_value
                
    return structured_data
