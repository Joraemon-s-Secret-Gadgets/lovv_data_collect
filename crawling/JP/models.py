"""
일본 도시 취득용 공통 데이터 모델.

이 파일은 Wikipedia 클라이언트, 정규화, 파이프라인 계층에서 재사용하는 레코드 구조를 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


STATUS_COLLECTED = "collected"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_MISSING = "missing"


@dataclass(frozen=True, slots=True)
class PrefectureReference:
    prefecture_id: str
    name_ko: str
    name_ja: str
    name_en: str
    region: str


@dataclass(slots=True)  # noqa: MUTABLE_OK
class NormalizedRecord:
    source_name: str
    source_url: str
    collected_at: str
    field_status: dict[str, str]
    data_confidence: str = "medium"
    verified_at: str | None = None
    verified_source_url: str | None = None
    verification_note: str | None = None


@dataclass(slots=True)  # noqa: MUTABLE_OK
class PrefectureRecord(NormalizedRecord):
    prefecture_id: str = ""
    name_ko: str = ""
    name_ja: str = ""
    name_en: str = ""
    region: str = ""
    latitude: float | None = None
    longitude: float | None = None
    description: str = ""
    geography_description: str = ""
    climate_table: dict[str, str] | None = None


@dataclass(slots=True)  # noqa: MUTABLE_OK
class CityRecord(NormalizedRecord):
    city_id: str = ""
    city_name_ko: str = ""
    city_name_ja: str = ""
    city_name_en: str = ""
    prefecture_id: str = ""
    location: str = ""
    latitude: float | None = None
    longitude: float | None = None
    description: str = ""
    geography_description: str = ""
    climate_table: dict[str, str] | None = None
    site_urls: list[str] = field(default_factory=list)


# 파일 이력
# 2026-06-04: CLI 모듈에서 공통 취득 모델을 분리했다.
