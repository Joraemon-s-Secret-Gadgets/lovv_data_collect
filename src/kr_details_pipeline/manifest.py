"""Manifest records for KR detail raw ingest."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from kr_details_pipeline.s3_keys import build_raw_detail_key


@dataclass(frozen=True)
class RawManifestRecord:
    local_path: str
    file_name: str
    city_name_en: str
    city_name_ko: str
    province: str
    attraction_count: int
    festival_count: int
    visitor_statistics_count: int
    checksum_sha256: str
    byte_size: int
    s3_key: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_raw_manifest(input_dir: Path, ingest_date: str) -> list[RawManifestRecord]:
    records: list[RawManifestRecord] = []
    for path in sorted(input_dir.glob("*.json"), key=lambda item: item.name.lower()):
        payload = _read_json_object(path)
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        city_name_en = str(meta.get("city_name_en") or path.stem)
        city_name_ko = str(meta.get("city_name_ko") or "")
        province = str(meta.get("province") or "")
        attractions = _count_list(payload.get("attractions"))
        festivals = _count_list(payload.get("festivals"))
        visitor_statistics = _count_visitor_statistics(payload.get("visitor_statistics"))
        records.append(
            RawManifestRecord(
                local_path=str(path),
                file_name=path.name,
                city_name_en=city_name_en,
                city_name_ko=city_name_ko,
                province=province,
                attraction_count=attractions,
                festival_count=festivals,
                visitor_statistics_count=visitor_statistics,
                checksum_sha256=sha256_file(path),
                byte_size=path.stat().st_size,
                s3_key=build_raw_detail_key(city_name_en, ingest_date),
            )
        )
    return records


def write_raw_manifest(records: list[RawManifestRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "record_count": len(records),
        "records": [record.to_dict() for record in records],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _count_visitor_statistics(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        if "monthly" in value and isinstance(value["monthly"], list):
            return len(value["monthly"])
        return len(value)
    return 0
