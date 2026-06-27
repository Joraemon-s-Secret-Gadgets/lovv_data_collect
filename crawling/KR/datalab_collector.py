"""
DataLab visitor statistics collector for South Korea municipalities.

This module queries the TourAPI DataLabService locgoRegnVisitrDDList endpoint
to collect daily visitor counts per signguCode and aggregates them into
monthly statistics.

Extracted and refactored from .cache/tour_api_korea_repo/scripts/scrape_and_aggregate_visitor.py
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import requests

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# Data Models
# ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SignguCodeEntry:
    """A single municipality entry in the signguCode mapping."""

    code: str
    city_name_ko: str
    city_name_en: str
    province_id: str


@dataclass
class MonthlyVisitorData:
    """Aggregated visitor statistics for a single municipality in a single month."""

    month: str  # "YYYY-MM"
    days: int
    locals_total: float = 0.0
    locals_daily_avg: float = 0.0
    out_of_town_total: float = 0.0
    out_of_town_daily_avg: float = 0.0
    foreigners_total: float = 0.0
    foreigners_daily_avg: float = 0.0
    total_visitors: float = 0.0
    total_daily_avg: float = 0.0


@dataclass
class VisitorStatistics:
    """Complete visitor statistics for a municipality over a year."""

    year: int
    annual_totals: dict[str, float] = field(default_factory=dict)
    annual_daily_averages: dict[str, float] = field(default_factory=dict)
    monthly_statistics: list[MonthlyVisitorData] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────────
# SignguCode Mapping
# ────────────────────────────────────────────────────────────────────────────


class SignguCodeMapping:
    """Loads and validates the nationwide signguCode → city mapping."""

    def __init__(self, mapping_path: Path | None = None) -> None:
        if mapping_path is None:
            mapping_path = Path(__file__).parent / "signgu_codes.json"
        self._path = mapping_path
        self._entries: dict[str, SignguCodeEntry] = {}
        self._load()

    def _load(self) -> None:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        for code, info in raw.items():
            if not code.isdigit():
                logger.warning("Invalid signguCode (non-numeric): %s — skipped", code)
                continue
            city_ko = info.get("city_name_ko", "")
            city_en = info.get("city_name_en", "")
            province_id = info.get("province_id", "")
            if not city_ko or not city_en:
                logger.warning("signguCode %s missing name fields — skipped", code)
                continue
            self._entries[code] = SignguCodeEntry(
                code=code,
                city_name_ko=city_ko,
                city_name_en=city_en,
                province_id=province_id,
            )
        logger.info("Loaded %d signguCode entries from %s", len(self._entries), self._path)

    def __contains__(self, code: str) -> bool:
        return code in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, code: str) -> SignguCodeEntry | None:
        return self._entries.get(code)

    @property
    def codes(self) -> set[str]:
        return set(self._entries.keys())

    @property
    def entries(self) -> dict[str, SignguCodeEntry]:
        return dict(self._entries)


# ────────────────────────────────────────────────────────────────────────────
# BigDataClient — API client with key rotation and retry
# ────────────────────────────────────────────────────────────────────────────

# Minimum delay between consecutive API requests (seconds)
MIN_REQUEST_DELAY: Final[float] = 0.5
MAX_RETRIES: Final[int] = 3
BACKOFF_BASE: Final[float] = 2.0  # 2s, 4s, 8s


class BigDataClient:
    """Tour API DataLabService client with key pool rotation and retry logic."""

    BASE_URL: Final[str] = "http://apis.data.go.kr/B551011/DataLabService"

    def __init__(self, api_keys: list[str] | None = None) -> None:
        self._keys = api_keys or self._load_keys_from_env()
        if not self._keys:
            raise RuntimeError(
                "No API keys available. Set TOUR_API_KEYS or TOUR_API_KEY "
                "in environment or .env file."
            )
        self._current_key_index = 0
        self._last_request_time: float = 0.0
        logger.info("BigDataClient initialized with %d API key(s)", len(self._keys))

    @staticmethod
    def _load_keys_from_env() -> list[str]:
        """Load API keys from environment variables."""
        # Try TOUR_API_KEYS first (comma-separated), then TOUR_API_KEY (single)
        keys_str = os.environ.get("TOUR_API_KEYS", "")
        if keys_str:
            return [k.strip() for k in keys_str.split(",") if k.strip()]
        single_key = os.environ.get("TOUR_API_KEY", "")
        if single_key:
            return [single_key.strip()]
        return []

    @property
    def current_key(self) -> str:
        return self._keys[self._current_key_index]

    @property
    def keys_remaining(self) -> int:
        return len(self._keys) - self._current_key_index

    def rotate_key(self) -> bool:
        """Advance to the next API key. Returns False if all keys exhausted."""
        if self._current_key_index + 1 < len(self._keys):
            self._current_key_index += 1
            logger.info(
                "Rotated to API key index %d (%s...)",
                self._current_key_index,
                self.current_key[:8],
            )
            return True
        logger.error("All %d API keys exhausted!", len(self._keys))
        return False

    def _is_quota_error(self, code: str, message: str) -> bool:
        """Check if the error indicates quota/rate limit exhaustion."""
        code_str = str(code).strip()
        msg_upper = str(message).upper()
        return code_str in ("22", "0022") or "LIMIT" in msg_upper or "EXCEEDED" in msg_upper

    def _enforce_rate_limit(self) -> None:
        """Wait to respect minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_DELAY:
            time.sleep(MIN_REQUEST_DELAY - elapsed)

    def request(self, endpoint: str, params: dict[str, Any], timeout: int = 45) -> dict:
        """Make an API request with retry and key rotation.

        Raises RuntimeError if all keys are exhausted or max retries exceeded.
        """
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(MAX_RETRIES):
            self._enforce_rate_limit()

            request_params = {
                **params,
                "serviceKey": self.current_key,
                "MobileOS": "ETC",
                "MobileApp": "Lovv",
                "_type": "json",
            }

            try:
                self._last_request_time = time.time()
                resp = requests.get(url, params=request_params, timeout=timeout)

                # HTTP 429 handling
                if resp.status_code == 429 or "API token quota exceeded" in resp.text:
                    logger.warning("HTTP 429 / quota exceeded. Rotating key...")
                    if not self.rotate_key():
                        raise RuntimeError("All API keys exhausted (HTTP 429).")
                    continue

                resp.raise_for_status()

                # XML error response handling
                content_type = resp.headers.get("Content-Type", "")
                if "xml" in content_type or resp.text.strip().startswith("<"):
                    code_match = re.search(r"<returnReasonCode>(.*?)</returnReasonCode>", resp.text)
                    msg_match = re.search(
                        r"<returnAuthMsg>(.*?)</returnAuthMsg>", resp.text
                    ) or re.search(r"<errMsg>(.*?)</errMsg>", resp.text)
                    code = code_match.group(1) if code_match else "99"
                    msg = msg_match.group(1) if msg_match else "XML_ERROR"

                    if self._is_quota_error(code, msg):
                        logger.warning("XML quota error: %s. Rotating key...", msg)
                        if not self.rotate_key():
                            raise RuntimeError("All API keys exhausted (XML quota).")
                        continue
                    raise RuntimeError(f"API XML Error {code}: {msg}")

                # Parse JSON response
                data = resp.json()
                header = data.get("response", {}).get("header", {})
                result_code = header.get("resultCode", "0000")
                result_msg = header.get("resultMsg", "OK")

                if result_code not in ("0000", "00", "OK"):
                    if self._is_quota_error(result_code, result_msg):
                        logger.warning("JSON quota error: %s. Rotating key...", result_msg)
                        if not self.rotate_key():
                            raise RuntimeError("All API keys exhausted (JSON quota).")
                        continue
                    raise RuntimeError(f"API Error {result_code}: {result_msg}")

                return data

            except (requests.ConnectionError, requests.Timeout, OSError) as e:
                wait = BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Transient error (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                    wait,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Max retries ({MAX_RETRIES}) exceeded for {endpoint}: {e}"
                    ) from e

        raise RuntimeError(f"Request to {endpoint} failed after {MAX_RETRIES} attempts.")


# ────────────────────────────────────────────────────────────────────────────
# Aggregation Logic
# ────────────────────────────────────────────────────────────────────────────


def get_days_in_month(year: int, month: int) -> int:
    """Return the number of days in a given month, accounting for leap years."""
    if month == 2:
        return 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    return [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]


def aggregate_monthly(
    daily_records: list[dict[str, Any]],
    month: str,
    days: int,
) -> MonthlyVisitorData:
    """Aggregate daily visitor records into a single monthly summary.

    Each record is expected to have 'touDivCd' (1=locals, 2=out_of_town,
    3=foreigners) and 'touNum' (visitor count as float).

    Args:
        daily_records: List of raw API response items for this month.
        month: Month string in "YYYY-MM" format.
        days: Number of days in the month.

    Returns:
        MonthlyVisitorData with totals and daily averages.
    """
    totals: dict[int, float] = defaultdict(float)
    for record in daily_records:
        tou_div_cd = int(record.get("touDivCd", 0))
        tou_num = float(record.get("touNum", 0.0))
        totals[tou_div_cd] += tou_num

    locals_total = totals.get(1, 0.0)
    out_of_town_total = totals.get(2, 0.0)
    foreigners_total = totals.get(3, 0.0)
    total_visitors = locals_total + out_of_town_total + foreigners_total

    return MonthlyVisitorData(
        month=month,
        days=days,
        locals_total=round(locals_total, 2),
        locals_daily_avg=round(locals_total / days, 2) if days > 0 else 0.0,
        out_of_town_total=round(out_of_town_total, 2),
        out_of_town_daily_avg=round(out_of_town_total / days, 2) if days > 0 else 0.0,
        foreigners_total=round(foreigners_total, 2),
        foreigners_daily_avg=round(foreigners_total / days, 2) if days > 0 else 0.0,
        total_visitors=round(total_visitors, 2),
        total_daily_avg=round(total_visitors / days, 2) if days > 0 else 0.0,
    )


# ────────────────────────────────────────────────────────────────────────────
# Collection Orchestrator
# ────────────────────────────────────────────────────────────────────────────


def collect_visitor_statistics(
    year: int,
    mapping: SignguCodeMapping,
    client: BigDataClient,
    output_path: Path,
    force_refresh: bool = False,
) -> dict[str, VisitorStatistics]:
    """Collect monthly visitor statistics for all municipalities nationwide.

    Queries the locgoRegnVisitrDDList endpoint month-by-month, filters by
    signguCode, aggregates daily → monthly, and persists results to
    *output_path*.

    Supports resumability: if *output_path* exists and a municipality already
    has complete 12-month data, it is skipped unless *force_refresh* is True.

    Returns a dict mapping city_name_en to VisitorStatistics.
    """
    # Load existing data for resumability
    existing_data: dict[str, Any] = {}
    if output_path.exists() and not force_refresh:
        try:
            existing_data = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not load existing visitor data: %s", e)

    # Determine which cities already have complete data (12 months)
    complete_cities: set[str] = set()
    if not force_refresh:
        for city_en, stats in existing_data.items():
            monthly = stats.get("monthly_statistics", [])
            if len(monthly) >= 12:
                complete_cities.add(city_en)

    if complete_cities:
        logger.info(
            "Skipping %d cities with complete %d data (use --force-refresh to re-collect)",
            len(complete_cities),
            year,
        )

    # Build month ranges
    months_info: list[tuple[str, str, str, int]] = []
    for m in range(1, 13):
        days = get_days_in_month(year, m)
        start_ymd = f"{year}{m:02d}01"
        end_ymd = f"{year}{m:02d}{days:02d}"
        month_str = f"{year}-{m:02d}"
        months_info.append((start_ymd, end_ymd, month_str, days))

    # Collect: month-by-month query, filter by signguCode, aggregate per city
    # city_en -> month_str -> list of raw records
    city_monthly_records: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for start_ymd, end_ymd, month_str, days in months_info:
        logger.info("Querying month %s (%s - %s)...", month_str, start_ymd, end_ymd)
        page_no = 1
        num_of_rows = 5000

        while True:
            params = {
                "startYmd": start_ymd,
                "endYmd": end_ymd,
                "numOfRows": num_of_rows,
                "pageNo": page_no,
            }

            try:
                resp_data = client.request("locgoRegnVisitrDDList", params)
            except RuntimeError as e:
                logger.error("Failed to query %s page %d: %s", month_str, page_no, e)
                break

            body = resp_data.get("response", {}).get("body", {})
            items = body.get("items", {})
            item_list = items.get("item", []) if isinstance(items, dict) else []

            if not isinstance(item_list, list):
                item_list = [item_list] if isinstance(item_list, dict) else []

            if not item_list:
                break

            # Filter by signguCode and group by city
            for item in item_list:
                sig_code = str(item.get("signguCode", "")).strip()
                if sig_code not in mapping:
                    continue
                entry = mapping.get(sig_code)
                if entry is None:
                    continue
                city_en = entry.city_name_en
                if city_en in complete_cities:
                    continue
                city_monthly_records[city_en][month_str].append(item)

            # Pagination check
            total_count = int(body.get("totalCount", 0))
            if page_no * num_of_rows >= total_count:
                break
            page_no += 1

    # Aggregate monthly records into VisitorStatistics
    results: dict[str, VisitorStatistics] = {}

    for city_en, months_data in city_monthly_records.items():
        monthly_stats: list[MonthlyVisitorData] = []
        for _, _, month_str, days in months_info:
            records = months_data.get(month_str, [])
            monthly_stats.append(aggregate_monthly(records, month_str, days))

        # Compute annual totals
        total_locals = sum(m.locals_total for m in monthly_stats)
        total_out = sum(m.out_of_town_total for m in monthly_stats)
        total_foreign = sum(m.foreigners_total for m in monthly_stats)
        total_visitors = sum(m.total_visitors for m in monthly_stats)
        total_days = sum(m.days for m in monthly_stats)

        results[city_en] = VisitorStatistics(
            year=year,
            annual_totals={
                "locals": round(total_locals, 2),
                "out_of_town": round(total_out, 2),
                "foreigners": round(total_foreign, 2),
                "total_visitors": round(total_visitors, 2),
            },
            annual_daily_averages={
                "locals": round(total_locals / total_days, 2) if total_days > 0 else 0.0,
                "out_of_town": round(total_out / total_days, 2) if total_days > 0 else 0.0,
                "foreigners": round(total_foreign / total_days, 2) if total_days > 0 else 0.0,
                "total_visitors": round(total_visitors / total_days, 2) if total_days > 0 else 0.0,
            },
            monthly_statistics=monthly_stats,
        )

    # Merge with existing data and persist
    output_data = dict(existing_data)
    for city_en, stats in results.items():
        output_data[city_en] = {
            "year": stats.year,
            "annual_totals": stats.annual_totals,
            "annual_daily_averages": stats.annual_daily_averages,
            "monthly_statistics": [
                {
                    "month": m.month,
                    "days": m.days,
                    "locals_total": m.locals_total,
                    "locals_daily_avg": m.locals_daily_avg,
                    "out_of_town_total": m.out_of_town_total,
                    "out_of_town_daily_avg": m.out_of_town_daily_avg,
                    "foreigners_total": m.foreigners_total,
                    "foreigners_daily_avg": m.foreigners_daily_avg,
                    "total_visitors": m.total_visitors,
                    "total_daily_avg": m.total_daily_avg,
                }
                for m in stats.monthly_statistics
            ],
        }

    # Persist to disk
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Persisted visitor statistics for %d cities to %s (total in file: %d)",
        len(results),
        output_path,
        len(output_data),
    )

    return results


def collect_visitor_statistics_for_city(
    signgu_code: str,
    city_name_en: str,
    year: int,
    client: BigDataClient,
) -> dict[str, Any] | None:
    """Collect visitor statistics for a single city by signguCode.

    Returns a dict matching the raw format expected by kr_details_pipeline:
    {
        "year": 2025,
        "annual_totals": {...},
        "annual_daily_averages": {...},
        "monthly_statistics": [{month, locals_total, ...}, ...]
    }

    Returns None if no data found or API error.
    """
    months_info: list[tuple[str, str, str, int]] = []
    for m in range(1, 13):
        days = get_days_in_month(year, m)
        start_ymd = f"{year}{m:02d}01"
        end_ymd = f"{year}{m:02d}{days:02d}"
        month_str = f"{year}{m:02d}"
        months_info.append((start_ymd, end_ymd, month_str, days))

    monthly_stats: list[dict[str, Any]] = []

    for start_ymd, end_ymd, month_str, days in months_info:
        params = {
            "startYmd": start_ymd,
            "endYmd": end_ymd,
            "numOfRows": 5000,
            "pageNo": 1,
        }

        try:
            resp_data = client.request("locgoRegnVisitrDDList", params)
        except (RuntimeError, Exception) as e:
            logger.warning("DataLab query failed for %s month %s: %s", city_name_en, month_str, e)
            continue

        body = resp_data.get("response", {}).get("body", {})
        items = body.get("items", {})
        item_list = items.get("item", []) if isinstance(items, dict) else []
        if not isinstance(item_list, list):
            item_list = [item_list] if isinstance(item_list, dict) else []

        # Filter by signguCode
        city_records = [
            item for item in item_list
            if str(item.get("signguCode", "")).strip() == signgu_code
        ]

        agg = aggregate_monthly(city_records, month_str, days)
        monthly_stats.append({
            "month": month_str,
            "days": days,
            "locals_total": agg.locals_total,
            "locals_daily_avg": agg.locals_daily_avg,
            "out_of_town_total": agg.out_of_town_total,
            "out_of_town_daily_avg": agg.out_of_town_daily_avg,
            "foreigners_total": agg.foreigners_total,
            "foreigners_daily_avg": agg.foreigners_daily_avg,
            "total_visitors": agg.total_visitors,
            "total_daily_avg": agg.total_daily_avg,
        })

    if not monthly_stats:
        return None

    # Compute annual totals
    total_locals = sum(m["locals_total"] for m in monthly_stats)
    total_out = sum(m["out_of_town_total"] for m in monthly_stats)
    total_foreign = sum(m["foreigners_total"] for m in monthly_stats)
    total_visitors = sum(m["total_visitors"] for m in monthly_stats)
    total_days = sum(m["days"] for m in monthly_stats)

    return {
        "year": year,
        "annual_totals": {
            "locals": round(total_locals, 2),
            "out_of_town": round(total_out, 2),
            "foreigners": round(total_foreign, 2),
            "total_visitors": round(total_visitors, 2),
        },
        "annual_daily_averages": {
            "locals": round(total_locals / total_days, 2) if total_days else 0,
            "out_of_town": round(total_out / total_days, 2) if total_days else 0,
            "foreigners": round(total_foreign / total_days, 2) if total_days else 0,
            "total_visitors": round(total_visitors / total_days, 2) if total_days else 0,
        },
        "monthly_statistics": monthly_stats,
    }
