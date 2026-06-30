from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Final, assert_never

from botocore.exceptions import ClientError

from kr_details_pipeline.enrichment_engine import (
    DEFAULT_MODEL_ID,
    PROMPT_VERSION,
    EnrichmentResult,
    enrich_attraction,
    should_skip_enrichment,
)
from kr_details_pipeline.enrichment_persistence import (
    MissingDynamoKeyError,
    update_attraction_enrichment,
)
from kr_vector_index.export import iter_gsi3_items

DEFAULT_TABLE_NAME: Final = "TourKoreaDomainDataV2"
DEFAULT_REGION: Final = "us-east-1"
DEFAULT_SOURCE_DATASET: Final = "raw/KR/details/20260625/"
DEFAULT_INDEX_NAME: Final = "EntityTypeDomainIndex"
MAX_CONSECUTIVE_FAILURES: Final = 3

EnrichFunc = Callable[..., EnrichmentResult]
PersistFunc = Callable[..., None]


@dataclass(frozen=True, slots=True)
class BackfillConfig:
    table_name: str = DEFAULT_TABLE_NAME
    region: str = DEFAULT_REGION
    profile: str | None = None
    model_id: str = DEFAULT_MODEL_ID
    prompt_version: str = PROMPT_VERSION
    source_dataset: str = DEFAULT_SOURCE_DATASET
    limit: int | None = None
    city_pk: str | None = None
    resume_after: str | None = None
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class BackfillSummary:
    effective_parameters: dict[str, Any]
    total_candidates: int
    processed: int
    planned_for_enrichment: int
    succeeded: int
    skipped: int
    failed: int
    unchanged: int
    written: int
    failed_items: list[dict[str, str]]
    stopped_after_consecutive_failures: bool
    resume_after: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_backfill(
    items: Iterable[dict[str, Any]],
    *,
    dynamodb_client: Any,
    bedrock_client: Any,
    config: BackfillConfig,
    enrich_func: EnrichFunc = enrich_attraction,
    persist_func: PersistFunc = update_attraction_enrichment,
) -> BackfillSummary:
    total_candidates = 0
    processed = 0
    planned_for_enrichment = 0
    succeeded = 0
    skipped = 0
    failed = 0
    unchanged = 0
    written = 0
    failed_items: list[dict[str, str]] = []
    consecutive_failures = 0
    stopped = False
    resume_after: str | None = None

    for item in _iter_candidates(items, config):
        total_candidates += 1
        processed += 1
        item_cursor = _item_cursor(item)

        if should_skip_enrichment(
            item,
            model_id=config.model_id,
            prompt_version=config.prompt_version,
        ):
            skipped += 1
            unchanged += 1
            consecutive_failures = 0
            continue

        if config.dry_run:
            planned_for_enrichment += 1
            consecutive_failures = 0
            continue

        result = enrich_func(
            bedrock_client,
            item,
            model_id=config.model_id,
            prompt_version=config.prompt_version,
        )
        try:
            persist_func(
                dynamodb_client,
                table_name=config.table_name,
                item=item,
                result=result,
            )
        except (ClientError, MissingDynamoKeyError) as exc:
            failed += 1
            consecutive_failures += 1
            failed_items.append(_failed_item(item, exc))
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                stopped = True
                resume_after = item_cursor
                break
            continue

        written += 1
        match result.status:
            case "succeeded":
                succeeded += 1
                consecutive_failures = 0
            case "failed":
                failed += 1
                consecutive_failures += 1
                failed_items.append(_failed_result_item(item, result))
            case "skipped":
                skipped += 1
                consecutive_failures = 0
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            stopped = True
            resume_after = item_cursor
            break

    return BackfillSummary(
        effective_parameters=_effective_parameters(config),
        total_candidates=total_candidates,
        processed=processed,
        planned_for_enrichment=planned_for_enrichment,
        succeeded=succeeded,
        skipped=skipped,
        failed=failed,
        unchanged=unchanged,
        written=written,
        failed_items=failed_items,
        stopped_after_consecutive_failures=stopped,
        resume_after=resume_after,
    )


def parse_args(argv: Sequence[str] | None = None) -> BackfillConfig:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table-name", default=DEFAULT_TABLE_NAME)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--source-dataset", default=DEFAULT_SOURCE_DATASET)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--city-pk", default=None)
    parser.add_argument("--resume-after", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return BackfillConfig(
        table_name=args.table_name,
        region=args.region,
        profile=args.profile,
        model_id=args.model_id,
        source_dataset=args.source_dataset,
        limit=args.limit,
        city_pk=args.city_pk,
        resume_after=args.resume_after,
        dry_run=args.dry_run,
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    session = _create_session(config)
    dynamodb_client = session.client("dynamodb")
    bedrock_client = None if config.dry_run else session.client("bedrock-runtime")
    items = iter_gsi3_items(
        dynamodb_client,
        table_name=config.table_name,
        entity_type="attraction",
        index_name=DEFAULT_INDEX_NAME,
    )
    summary = run_backfill(
        items,
        dynamodb_client=dynamodb_client,
        bedrock_client=bedrock_client,
        config=config,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _create_session(config: BackfillConfig) -> Any:
    import boto3

    session_kwargs: dict[str, str] = {"region_name": config.region}
    if config.profile:
        session_kwargs["profile_name"] = config.profile
    return boto3.Session(**session_kwargs)


def _iter_candidates(
    items: Iterable[dict[str, Any]],
    config: BackfillConfig,
) -> Iterable[dict[str, Any]]:
    yielded = 0
    resume_reached = config.resume_after is None
    for item in items:
        if config.city_pk and item.get("PK") != config.city_pk:
            continue
        if not resume_reached:
            if _item_cursor(item) == config.resume_after:
                resume_reached = True
            continue
        if config.limit is not None and yielded >= config.limit:
            break
        yielded += 1
        yield item


def _effective_parameters(config: BackfillConfig) -> dict[str, Any]:
    return {
        "table_name": config.table_name,
        "region": config.region,
        "profile": config.profile,
        "model_id": config.model_id,
        "prompt_version": config.prompt_version,
        "source_dataset": config.source_dataset,
        "limit": config.limit,
        "city_pk": config.city_pk,
        "resume_after": config.resume_after,
        "dry_run": config.dry_run,
    }


def _item_cursor(item: dict[str, Any]) -> str:
    return str(item.get("SK") or item.get("content_id") or item.get("PK") or "unknown")


def _failed_item(item: dict[str, Any], exc: ClientError | MissingDynamoKeyError) -> dict[str, str]:
    return {
        "PK": str(item.get("PK") or ""),
        "SK": str(item.get("SK") or ""),
        "content_id": str(item.get("content_id") or ""),
        "error": _error_text(exc),
    }


def _failed_result_item(item: dict[str, Any], result: EnrichmentResult) -> dict[str, str]:
    return {
        "PK": str(item.get("PK") or ""),
        "SK": str(item.get("SK") or ""),
        "content_id": str(item.get("content_id") or ""),
        "error": str(result.metadata_enrichment.get("error_code") or result.status),
    }


def _error_text(exc: ClientError | MissingDynamoKeyError) -> str:
    match exc:
        case ClientError():
            return str(exc.response.get("Error", {}).get("Code") or exc)
        case MissingDynamoKeyError():
            return str(exc)
        case unreachable:
            assert_never(unreachable)


if __name__ == "__main__":
    raise SystemExit(main())
