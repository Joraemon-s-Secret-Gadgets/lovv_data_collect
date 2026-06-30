from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any, TypedDict

from boto3.dynamodb.types import TypeDeserializer

from kr_vector_index.export import should_vectorize
from kr_vector_index.manifest import build_manifest

DEFAULT_BATCH_SIZE = 250


class VectorBatchDescriptor(TypedDict):
    batch_id: str
    city_pk: str
    start_offset: int
    max_items: int
    table_name: str
    entity_index_name: str
    vector_bucket: str
    index_name: str


def build_batch_plan(
    items: Sequence[dict[str, Any]],
    *,
    batch_size: int,
    table_name: str,
    entity_index_name: str,
    vector_bucket: str,
    index_name: str,
) -> list[VectorBatchDescriptor]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    city_counts: Counter[str] = Counter()
    for item in items:
        city_pk = str(item.get("PK") or "")
        if city_pk:
            city_counts[city_pk] += 1

    descriptors: list[VectorBatchDescriptor] = []
    for city_pk in sorted(city_counts):
        count = city_counts[city_pk]
        for start_offset in range(0, count, batch_size):
            descriptors.append(
                {
                    "batch_id": f"kr-vector-{len(descriptors) + 1:06d}",
                    "city_pk": city_pk,
                    "start_offset": start_offset,
                    "max_items": batch_size,
                    "table_name": table_name,
                    "entity_index_name": entity_index_name,
                    "vector_bucket": vector_bucket,
                    "index_name": index_name,
                }
            )
    return descriptors


def fetch_vectorizable_items_by_pk(
    client: Any,
    *,
    table_name: str,
    city_pk: str,
) -> list[dict[str, Any]]:
    deserializer = TypeDeserializer()
    exclusive_start_key: dict[str, Any] | None = None
    items: list[dict[str, Any]] = []
    while True:
        params: dict[str, Any] = {
            "TableName": table_name,
            "KeyConditionExpression": "PK = :pk",
            "ExpressionAttributeValues": {
                ":pk": {"S": city_pk},
            },
        }
        if exclusive_start_key:
            params["ExclusiveStartKey"] = exclusive_start_key
        response = client.query(**params)
        for raw_item in response.get("Items", []):
            item = {key: deserializer.deserialize(value) for key, value in raw_item.items()}
            if should_vectorize(item):
                items.append(item)
        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break
    return sorted(items, key=lambda item: str(item.get("SK") or ""))


def slice_batch_items(
    items: Sequence[dict[str, Any]],
    *,
    start_offset: int,
    max_items: int,
) -> list[dict[str, Any]]:
    if start_offset < 0:
        raise ValueError("start_offset must be >= 0")
    if max_items < 1:
        raise ValueError("max_items must be >= 1")
    return list(items[start_offset : start_offset + max_items])


def aggregate_batch_results(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    batch_count = 0
    item_count = 0
    chunk_count = 0
    vector_success_count = 0
    failed_count = 0
    failed_batch_count = 0
    failed_batch_ids: list[str] = []

    for result in results:
        summary = result.get("summary", result)
        batch_count += 1
        item_count += int(summary.get("item_count", 0) or 0)
        chunk_count += int(summary.get("chunk_count", 0) or 0)
        vector_success_count += int(summary.get("vector_success_count", 0) or 0)
        current_failed_count = int(summary.get("failed_count", 0) or 0)
        failed_count += current_failed_count
        if current_failed_count:
            failed_batch_count += 1
            failed_batch_ids.append(str(summary.get("batch_id") or "unknown"))

    status = "succeeded"
    if failed_count:
        status = "partial"
    if batch_count > 0 and failed_batch_count == batch_count and vector_success_count == 0:
        status = "failed"

    return {
        "status": status,
        "batch_count": batch_count,
        "item_count": item_count,
        "chunk_count": chunk_count,
        "vector_success_count": vector_success_count,
        "failed_count": failed_count,
        "failed_batch_count": failed_batch_count,
        "failed_batch_ids": failed_batch_ids,
    }


def build_batch_manifest(
    *,
    index_name: str,
    entity_counts: dict[str, int],
    aggregate_summary: dict[str, Any],
) -> dict[str, Any]:
    manifest = build_manifest(
        index_name=index_name,
        entity_counts=entity_counts,
        chunk_count=int(aggregate_summary.get("chunk_count", 0) or 0),
        vector_success_count=int(aggregate_summary.get("vector_success_count", 0) or 0),
        failed_count=int(aggregate_summary.get("failed_count", 0) or 0),
    )
    manifest["status"] = str(aggregate_summary.get("status") or "unknown")
    manifest["batch_count"] = int(aggregate_summary.get("batch_count", 0) or 0)
    manifest["item_count"] = int(aggregate_summary.get("item_count", 0) or 0)
    manifest["failed_batch_ids"] = list(aggregate_summary.get("failed_batch_ids", []))
    return manifest
