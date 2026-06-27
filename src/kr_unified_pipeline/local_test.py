"""
Local test runner for single-province E2E pipeline validation.

Executes the full End-to-End pipeline flow (S3 read → DynamoDB load →
Vector rebuild) scoped to a single province, enabling local validation
before full multi-province execution.

Uses local AWS credentials (CLI profile or environment variables).

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.9
"""

from __future__ import annotations

import logging
import time
from typing import Any

from kr_unified_pipeline.dynamodb_loader import DynamoDBLoader
from kr_unified_pipeline.models import LocalTestSummary
from kr_unified_pipeline.s3_reader import S3ProcessedReader
from kr_unified_pipeline.vector_rebuilder import VectorRebuilder

logger = logging.getLogger(__name__)


class LocalTestRunner:
    """Executes full E2E pipeline scoped to a single province.

    Runs the sequence: S3 read → DynamoDB load → Vector rebuild, filtering
    all operations by the specified province_key. Outputs a LocalTestSummary
    with a PASS/FAIL verdict.

    The verdict is PASS only when zero failures occur across all operations.

    Args:
        province_id: Province key to scope all operations (e.g. "KR-42").
        bucket: S3 pipeline bucket name.
        ingest_date: Target ingest date partition (e.g. "20250115").
            If empty, the latest available date is auto-detected.
        table_name: DynamoDB table name for loading.
        vector_bucket: S3 Vectors bucket name for vector index.
        index_name: Vector index name (e.g. "kr-tour-domain-v1").
        session: A boto3 Session configured with local credentials.
    """

    def __init__(
        self,
        province_id: str,
        bucket: str,
        ingest_date: str,
        table_name: str,
        vector_bucket: str,
        index_name: str,
        session: Any,
    ) -> None:
        self._province_id = province_id
        self._bucket = bucket
        self._ingest_date = ingest_date
        self._table_name = table_name
        self._vector_bucket = vector_bucket
        self._index_name = index_name
        self._session = session

    @property
    def province_id(self) -> str:
        return self._province_id

    def run(self) -> LocalTestSummary:
        """Execute the province-scoped E2E pipeline and return summary.

        Sequence:
            1. S3 read - filtered by province_id
            2. DynamoDB load - write filtered items
            3. Vector rebuild - province-scoped

        Returns:
            LocalTestSummary with verdict, item counts, and any failures.
        """
        start_time = time.time()
        failed_items: list[str] = []

        logger.info(
            "Starting local test for province '%s' (bucket=%s, date=%s, table=%s)",
            self._province_id,
            self._bucket,
            self._ingest_date,
            self._table_name,
        )

        # --- Phase 1: S3 Read (province-filtered) ---
        s3_client = self._session.client("s3")
        reader = S3ProcessedReader(
            s3_client=s3_client,
            bucket=self._bucket,
            ingest_date=self._ingest_date,
        )
        items = reader.read_items(province_id=self._province_id)
        items_read = len(items)
        logger.info("Phase 1 (S3 read): %d items read for province '%s'", items_read, self._province_id)

        # --- Phase 2: DynamoDB Load ---
        dynamodb_client = self._session.client("dynamodb")
        loader = DynamoDBLoader(client=dynamodb_client, table_name=self._table_name)
        load_result = loader.load_items(items)
        items_loaded = load_result.items_loaded

        for failure in load_result.failures:
            failed_items.append(f"dynamo:{failure.pk}/{failure.sk}")

        logger.info(
            "Phase 2 (DynamoDB load): %d loaded, %d failed",
            load_result.items_loaded,
            load_result.items_failed,
        )

        # --- Phase 3: Vector Rebuild (province-scoped) ---
        bedrock_client = self._session.client("bedrock-runtime")
        s3vectors_client = self._session.client("s3vectors")
        rebuilder = VectorRebuilder(
            dynamodb_client=dynamodb_client,
            bedrock_client=bedrock_client,
            s3vectors_client=s3vectors_client,
        )
        rebuild_result = rebuilder.rebuild(
            mode="full",
            table_name=self._table_name,
            vector_bucket=self._vector_bucket,
            index_name=self._index_name,
        )
        vectors_built = rebuild_result.items_upserted

        for error in rebuild_result.errors_encountered:
            failed_items.append(f"vector:{error}")

        logger.info(
            "Phase 3 (Vector rebuild): %d upserted, %d skipped",
            rebuild_result.items_upserted,
            rebuild_result.items_skipped,
        )

        # --- Determine Verdict ---
        elapsed = time.time() - start_time
        verdict = "PASS" if len(failed_items) == 0 else "FAIL"

        summary = LocalTestSummary(
            province_id=self._province_id,
            items_read_from_s3=items_read,
            items_loaded_to_dynamodb=items_loaded,
            vectors_built=vectors_built,
            verdict=verdict,
            failed_items=failed_items,
            execution_time_seconds=round(elapsed, 2),
        )

        # --- Log verdict and recommendation ---
        if verdict == "PASS":
            logger.info(
                "Local test PASSED for province '%s': "
                "%d items read, %d loaded, %d vectors built (%.2fs)",
                self._province_id,
                items_read,
                items_loaded,
                vectors_built,
                elapsed,
            )
        else:
            logger.warning(
                "Local test FAILED for province '%s': "
                "%d items read, %d loaded, %d vectors built, %d failures (%.2fs)",
                self._province_id,
                items_read,
                items_loaded,
                vectors_built,
                len(failed_items),
                elapsed,
            )
            logger.warning(
                "RECOMMENDATION: Resolve the %d failure(s) listed above before "
                "running the full multi-province execution. Failed items: %s",
                len(failed_items),
                ", ".join(failed_items[:10]),  # Limit output for readability
            )

        return summary
