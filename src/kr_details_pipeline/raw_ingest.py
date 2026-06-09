"""S3 Raw ingest service for KR details JSON files."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
import json

from kr_details_pipeline.manifest import RawManifestRecord, build_raw_manifest, write_raw_manifest


class S3Client(Protocol):
    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        ...

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class RawIngestConfig:
    input_dir: Path
    output_dir: Path
    bucket: str
    ingest_date: str
    overwrite: bool = False


@dataclass(frozen=True)
class UploadResult:
    local_path: str
    bucket: str
    s3_key: str
    checksum_sha256: str
    byte_size: int
    city_name_en: str
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ingest_raw_details(config: RawIngestConfig, s3_client: S3Client) -> list[UploadResult]:
    records = build_raw_manifest(config.input_dir, config.ingest_date)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    write_raw_manifest(records, config.output_dir / "raw_manifest.json")

    results: list[UploadResult] = []
    failures: list[UploadResult] = []
    for record in records:
        result = _upload_record(record, config.bucket, s3_client, overwrite=config.overwrite)
        results.append(result)
        if result.status == "failed":
            failures.append(result)

    _write_jsonl(config.output_dir / "upload_results.jsonl", [result.to_dict() for result in results])
    _write_jsonl(config.output_dir / "failed_uploads.jsonl", [result.to_dict() for result in failures])
    return results


def _upload_record(record: RawManifestRecord, bucket: str, s3_client: S3Client, overwrite: bool) -> UploadResult:
    path = Path(record.local_path)
    try:
        if not overwrite and _remote_checksum_matches(s3_client, bucket, record.s3_key, record.checksum_sha256):
            return _result(record, bucket, "skipped")

        s3_client.put_object(
            Bucket=bucket,
            Key=record.s3_key,
            Body=path.read_bytes(),
            ContentType="application/json",
            Metadata={
                "country": "KR",
                "entity": "details",
                "city_name_en": record.city_name_en,
                "source_checksum_sha256": record.checksum_sha256,
                "source_byte_size": str(record.byte_size),
                "ingest_date": record.s3_key.split("/")[3],
            },
        )
        return _result(record, bucket, "uploaded")
    except Exception as exc:
        return _result(record, bucket, "failed", exc.__class__.__name__)


def _remote_checksum_matches(s3_client: S3Client, bucket: str, key: str, checksum: str) -> bool:
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
    except Exception:
        return False
    metadata = response.get("Metadata") or {}
    return metadata.get("source_checksum_sha256") == checksum


def _result(record: RawManifestRecord, bucket: str, status: str, error: str | None = None) -> UploadResult:
    return UploadResult(
        local_path=record.local_path,
        bucket=bucket,
        s3_key=record.s3_key,
        checksum_sha256=record.checksum_sha256,
        byte_size=record.byte_size,
        city_name_en=record.city_name_en,
        status=status,
        error=error,
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            file.write("\n")
