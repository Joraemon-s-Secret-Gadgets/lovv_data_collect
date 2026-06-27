"""Upsert vectors into an S3 Vector index."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from kr_vector_index.chunks import VectorChunk

T = TypeVar("T")


def chunked(items: list[T], size: int) -> Iterator[list[T]]:
    if size < 1:
        raise ValueError("size must be >= 1")
    for index in range(0, len(items), size):
        yield items[index : index + size]


def build_vector_record(chunk: VectorChunk, embedding: list[float]) -> dict[str, Any]:
    return {
        "key": chunk.key,
        "data": {"float32": [float(value) for value in embedding]},
        "metadata": chunk.metadata,
    }


def put_vectors_cli(
    records: list[dict[str, Any]],
    *,
    vector_bucket: str,
    index_name: str,
    region: str = "us-east-1",
    profile: str | None = None,
    batch_size: int = 500,
) -> int:
    written = 0
    for batch in chunked(records, batch_size):
        with tempfile.TemporaryDirectory(prefix="lovv-s3vectors-upsert-") as tmp:
            payload_path = Path(tmp) / "vectors.json"
            payload_path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
            command = ["aws", "s3vectors"]
            if profile:
                command.extend(["--profile", profile])
            command.extend(
                [
                    "--region",
                    region,
                    "put-vectors",
                    "--vector-bucket-name",
                    vector_bucket,
                    "--index-name",
                    index_name,
                    "--vectors",
                    f"file://{payload_path.as_posix()}",
                ]
            )
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr or completed.stdout)
            written += len(batch)
    return written


def put_vectors_sdk(
    client: Any,
    records: list[dict[str, Any]],
    *,
    vector_bucket: str,
    index_name: str,
    batch_size: int = 500,
) -> int:
    written = 0
    for batch in chunked(records, batch_size):
        # Deduplicate keys within batch (S3 Vectors rejects duplicate keys)
        seen_keys: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for record in batch:
            key = record.get("key", "")
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(record)
        if deduped:
            client.put_vectors(
                vectorBucketName=vector_bucket,
                indexName=index_name,
                vectors=deduped,
            )
            written += len(deduped)
    return written


def build_vector_records(chunks: list[VectorChunk], embeddings: Iterable[list[float]]) -> list[dict[str, Any]]:
    return [build_vector_record(chunk, embedding) for chunk, embedding in zip(chunks, embeddings, strict=True)]
