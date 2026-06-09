"""
Shared data models for South Korea city acquisition.

This file defines reusable record structures and imports the base records
from JP to ensure identical JSON keys and database compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass

# Re-export base models and statuses for strict schema compatibility
from crawling.JP.models import (
    STATUS_COLLECTED,
    STATUS_MISSING,
    STATUS_NEEDS_REVIEW,
    CityRecord,
    NormalizedRecord,
    PrefectureRecord,
)


@dataclass(frozen=True)
class ProvinceReference:
    prefecture_id: str  # Kept as prefecture_id for DB constraint compatibility
    name_ko: str
    name_en: str
    region: str
