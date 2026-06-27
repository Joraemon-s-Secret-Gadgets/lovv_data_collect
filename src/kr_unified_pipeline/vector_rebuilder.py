"""Vector index rebuilder for the unified preprocessing pipeline.

Reuses kr_vector_index modules (export, chunks, embed, upsert) to rebuild
the S3 Vectors index from DynamoDB domain data. Supports full and incremental
rebuild modes using the EntityTypeDomainIndex GSI on the V2 table.

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from kr_vector_index.chunks import build_chunks
from kr_vector_index.embed import EmbeddingError, embed_chunks
from kr_vector_index.export import export_items
from kr_vector_index.upsert import build_vector_records, put_vectors_sdk

from kr_unified_pipeline.models import RebuildManifest

logger = logging.getLogger(__name__)

# GSI name for the new TourKoreaDomainDataV2 table
DEFAULT_GSI_NAME = "EntityTypeDomainIndex"


class VectorRebuilder:
    """Rebuilds the S3 Vectors index from DynamoDB domain items.

    Uses kr_vector_index modules for export, chunking, embedding, and upsert.
    Supports full and incremental rebuild modes.

    Args:
        dynamodb_client: boto3 DynamoDB client (low-level).
        bedrock_client: boto3 Bedrock Runtime client for embeddings.
        s3vectors_client: boto3 S3 Vectors client for upserting vectors.
    """

    def __init__(
        self,
        dynamodb_client: Any,
        bedrock_client: Any,
        s3vectors_client: Any,
    ) -> None:
        self._dynamodb_client = dynamodb_client
        self._bedrock_client = bedrock_client
        self._s3vectors_client = s3vectors_client

    def rebuild(
        self,
        *,
        mode: str,
        table_name: str,
        vector_bucket: str,
        index_name: str,
        last_rebuild_timestamp: str | None = None,
    ) -> RebuildManifest:
        """Execute a vector index rebuild.

        Args:
            mode: Rebuild mode - "full" or "incremental".
            table_name: DynamoDB table name to export items from.
            vector_bucket: S3 Vectors bucket name for upsert.
            index_name: S3 Vectors index name for upsert.
            last_rebuild_timestamp: ISO 8601 timestamp for incremental mode.
                Only items modified after this timestamp are processed.

        Returns:
            RebuildManifest with rebuild execution details.
        """
        manifest = RebuildManifest(
            rebuild_mode=mode,
            start_timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # 1. Export items from DynamoDB using EntityTypeDomainIndex GSI
        logger.info(
            "Exporting items from %s (mode=%s, gsi=%s)",
            table_name,
            mode,
            DEFAULT_GSI_NAME,
        )
        items = export_items(
            self._dynamodb_client,
            table_name=table_name,
            index_name=DEFAULT_GSI_NAME,
        )

        # 2. For incremental mode, filter by modification timestamp
        if mode == "incremental" and last_rebuild_timestamp:
            items = self._filter_by_timestamp(items, last_rebuild_timestamp)

        manifest.total_items_processed = len(items)
        logger.info("Exported %d items for %s rebuild", len(items), mode)

        if not items:
            manifest.end_timestamp = datetime.now(timezone.utc).isoformat()
            return manifest

        # 3. Build chunks from exported items
        chunks = build_chunks(items)

        # 4. Embed chunks one at a time to handle failures gracefully
        embeddings: list[list[float]] = []
        valid_chunks = []
        for i, chunk in enumerate(chunks):
            try:
                embedding = embed_chunks(self._bedrock_client, [chunk])
                embeddings.extend(embedding)
                valid_chunks.append(chunk)
            except (EmbeddingError, Exception) as exc:
                item = items[i]
                pk = item.get("PK", "unknown")
                sk = item.get("SK", "unknown")
                error_msg = f"Embedding failed for PK={pk}, SK={sk}: {exc}"
                logger.warning(error_msg)
                manifest.items_skipped += 1
                manifest.errors_encountered.append(error_msg)

        # 5. Build vector records and upsert
        if valid_chunks and embeddings:
            records = build_vector_records(valid_chunks, embeddings)
            try:
                upserted = put_vectors_sdk(
                    self._s3vectors_client,
                    records,
                    vector_bucket=vector_bucket,
                    index_name=index_name,
                )
                manifest.items_upserted = upserted
            except Exception as exc:
                error_msg = f"Vector upsert failed: {exc}"
                logger.error(error_msg)
                manifest.errors_encountered.append(error_msg)

        manifest.end_timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Rebuild complete: processed=%d, upserted=%d, skipped=%d",
            manifest.total_items_processed,
            manifest.items_upserted,
            manifest.items_skipped,
        )
        return manifest

    @staticmethod
    def _filter_by_timestamp(
        items: list[dict[str, Any]],
        last_rebuild_timestamp: str,
    ) -> list[dict[str, Any]]:
        """Filter items to only those modified after the given timestamp.

        Uses the 'updated_at' or 'collected_at' field from each item
        to determine modification time.
        """
        filtered: list[dict[str, Any]] = []
        for item in items:
            modified_at = item.get("updated_at") or item.get("collected_at") or ""
            if not modified_at:
                # Include items with no timestamp (can't determine age)
                filtered.append(item)
                continue
            if str(modified_at) > last_rebuild_timestamp:
                filtered.append(item)
        return filtered
