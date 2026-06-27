#!/usr/bin/env python3
"""Build S3 Vector index for AgentCore v1 (강원/경북 only).

Exports domain items from TourKoreaDomainData (V1 table), filters to
강원특별자치도 and 경상북도 provinces, then builds embeddings and upserts
vectors to the lovv-agentcore-v1-vector bucket / kr-agentcore-v1 index.

Usage:
    # Dry-run: show item counts without building vectors
    python scripts/build_agentcore_v1_vectors.py --profile skn26_final --dry-run

    # Full build: embed and upsert to S3 Vectors
    python scripts/build_agentcore_v1_vectors.py --profile skn26_final

    # Build specific city only
    python scripts/build_agentcore_v1_vectors.py --profile skn26_final --city-pk "CITY#Andong"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import boto3

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kr_vector_index.chunks import build_chunks
from kr_vector_index.embed import embed_chunks, EmbeddingError
from kr_vector_index.export import export_items, count_by_entity_type
from kr_vector_index.upsert import build_vector_records, put_vectors_sdk


# Target provinces for AgentCore v1
TARGET_PROVINCES = {"강원특별자치도", "경상북도"}

# V1 table and AgentCore v1 vector config
TABLE_NAME = "TourKoreaDomainData"
VECTOR_BUCKET = "lovv-agentcore-v1-vector"
INDEX_NAME = "kr-agentcore-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build AgentCore v1 vector index from V1 table (강원/경북 only)."
    )
    parser.add_argument("--profile", default=None, help="AWS CLI profile name.")
    parser.add_argument("--region", default="us-east-1", help="AWS region.")
    parser.add_argument("--table-name", default=TABLE_NAME, help="DynamoDB table name.")
    parser.add_argument("--vector-bucket", default=VECTOR_BUCKET, help="S3 Vector bucket name.")
    parser.add_argument("--index-name", default=INDEX_NAME, help="S3 Vector index name.")
    parser.add_argument("--city-pk", default=None, help="Filter to specific city PK.")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without embedding/upsert.")
    parser.add_argument("--batch-size", type=int, default=50, help="Embedding batch size.")
    return parser.parse_args()


def filter_by_province(items: list[dict], target_provinces: set[str]) -> list[dict]:
    """Filter items to only those belonging to target provinces.

    Matches items where 'province' field contains a target province name.
    Also includes items without a province field that came from V1 강원/경북 data
    (identified by province_key being absent in the original DynamoDB item).
    """
    filtered = []
    for item in items:
        province = str(item.get("province") or "")
        # Match items with province field containing target province
        if any(p in province for p in target_provinces):
            filtered.append(item)
            continue
        # Also include items with province_key matching target pattern
        province_key = str(item.get("province_key") or "")
        if any(p in province_key for p in target_provinces):
            filtered.append(item)
    return filtered


def main() -> int:
    args = parse_args()

    session_kwargs = {}
    if args.profile:
        session_kwargs["profile_name"] = args.profile
    if args.region:
        session_kwargs["region_name"] = args.region
    session = boto3.Session(**session_kwargs)

    print()
    print("=" * 60)
    print("  AgentCore v1 Vector Index Builder")
    print(f"  Table:        {args.table_name}")
    print(f"  Vector Bucket: {args.vector_bucket}")
    print(f"  Index:        {args.index_name}")
    print(f"  Region:       {args.region}")
    print(f"  Profile:      {args.profile or '(default)'}")
    print(f"  Mode:         {'DRY-RUN' if args.dry_run else 'BUILD'}")
    print(f"  Provinces:    {', '.join(sorted(TARGET_PROVINCES))}")
    print("=" * 60)
    print()

    # 1. Export items from V1 table
    print("[EXPORT] Exporting items from DynamoDB...")
    ddb = session.client("dynamodb")
    items = export_items(ddb, table_name=args.table_name, city_pk=args.city_pk)
    print(f"[EXPORT] Total items exported: {len(items)}")

    # 2. Filter to 강원/경북 only
    print("[FILTER] Filtering to 강원특별자치도 / 경상북도 items...")
    items = filter_by_province(items, TARGET_PROVINCES)
    print(f"[FILTER] Items after province filter: {len(items)}")

    if not items:
        print("[DONE] No items to process.")
        return 0

    # 3. Show entity type breakdown
    counts = count_by_entity_type(items)
    print(f"\n[COUNTS] Entity type breakdown:")
    for entity_type, count in sorted(counts.items()):
        print(f"  - {entity_type}: {count}")
    print(f"  - TOTAL: {sum(counts.values())}")

    if args.dry_run:
        # Build chunks for count only
        chunks = build_chunks(items)
        print(f"\n[DRY-RUN] Would build {len(chunks)} vector chunks.")
        print("[DRY-RUN] No embeddings generated. No vectors upserted.")
        return 0

    # 4. Build chunks
    print(f"\n[CHUNKS] Building vector chunks...")
    chunks = build_chunks(items)
    print(f"[CHUNKS] Built {len(chunks)} chunks.")

    # 5. Embed in batches
    print(f"[EMBED] Generating embeddings (batch_size={args.batch_size})...")
    bedrock = session.client("bedrock-runtime")
    embeddings: list[list[float]] = []
    failed_count = 0

    for i in range(0, len(chunks), args.batch_size):
        batch = chunks[i : i + args.batch_size]
        batch_embeddings = []
        for chunk in batch:
            try:
                emb = embed_chunks(bedrock, [chunk])
                batch_embeddings.extend(emb)
            except EmbeddingError as e:
                print(f"  [WARN] Embedding failed for {chunk.key}: {e}")
                batch_embeddings.append(None)
                failed_count += 1

        # Filter out failed embeddings
        for emb in batch_embeddings:
            if emb is not None:
                embeddings.append(emb)

        processed = min(i + args.batch_size, len(chunks))
        print(f"  [EMBED] {processed}/{len(chunks)} chunks processed...")

    # Align chunks with successful embeddings
    valid_chunks = [c for c, e in zip(chunks, [True] * len(embeddings) + [False] * failed_count) if e]
    valid_chunks = valid_chunks[:len(embeddings)]

    print(f"[EMBED] Successful: {len(embeddings)}, Failed: {failed_count}")

    if not embeddings:
        print("[ERROR] No successful embeddings. Aborting.")
        return 1

    # 6. Build vector records and upsert
    print(f"\n[UPSERT] Building vector records and upserting to S3 Vectors...")
    records = build_vector_records(valid_chunks, embeddings)
    s3vectors = session.client("s3vectors")
    written = put_vectors_sdk(
        s3vectors,
        records,
        vector_bucket=args.vector_bucket,
        index_name=args.index_name,
    )

    print(f"[UPSERT] Successfully upserted {written} vectors.")
    print()
    print("=" * 60)
    print("  BUILD COMPLETE")
    print(f"  Vectors written: {written}")
    print(f"  Failed:          {failed_count}")
    print(f"  Bucket:          {args.vector_bucket}")
    print(f"  Index:           {args.index_name}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
