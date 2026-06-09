"""S3 key builders for KR detail raw ingest."""

from __future__ import annotations

import re


def safe_city_name(value: str) -> str:
    normalized = value.strip().replace(" ", "_")
    normalized = re.sub(r"[^A-Za-z0-9_\-]", "", normalized)
    return normalized or "UNKNOWN_CITY"


def build_raw_detail_key(city_name_en: str, ingest_date: str) -> str:
    city = safe_city_name(city_name_en)
    date = ingest_date.strip().replace("-", "")
    if not re.fullmatch(r"\d{8}", date):
        raise ValueError("ingest_date must be YYYYMMDD or YYYY-MM-DD.")
    return f"raw/KR/details/{date}/{city}.json"
