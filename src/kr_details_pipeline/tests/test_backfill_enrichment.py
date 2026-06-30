from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from kr_details_pipeline.enrichment_engine import (
    DEFAULT_MODEL_ID,
    PROMPT_VERSION,
    EnrichmentResult,
    compute_input_hash,
)
from scripts.backfill_enrichment import BackfillConfig, run_backfill


def _make_item(content_id: str, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "PK": "CITY#GANGNEUNG",
        "SK": f"ATTRACTION#{content_id}",
        "entity_type": "attraction",
        "content_id": content_id,
        "title": f"관광지 {content_id}",
        "description": "바다 산책로",
        "theme": "자연·트레킹",
        "theme_tags": ["자연·트레킹"],
        "experience_guide": "걷기",
        "opening_hours": "09:00~18:00",
        "closed_days": "",
        "parking": "가능",
        "address": "강원특별자치도 강릉시",
    }
    item.update(overrides)
    return item


def _success_result() -> EnrichmentResult:
    return EnrichmentResult(
        status="succeeded",
        indoor_outdoor="outdoor",
        vibe_tags=["refreshing"],
        experience_tags=["walking"],
        companion_fit=["family"],
        metadata_enrichment={
            "status": "succeeded",
            "model_id": DEFAULT_MODEL_ID,
            "prompt_version": PROMPT_VERSION,
            "schema_version": "1",
            "generated_at": "2026-06-28T00:00:00Z",
            "input_hash": "sha256:test",
        },
    )


def _client_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}},
        "UpdateItem",
    )


def test_dry_run_reads_candidates_without_model_or_write_calls() -> None:
    model_calls: list[str] = []
    write_calls: list[str] = []

    def enrich_func(*args: Any, **kwargs: Any) -> EnrichmentResult:
        model_calls.append("called")
        return _success_result()

    def persist_func(*args: Any, **kwargs: Any) -> None:
        write_calls.append("called")

    summary = run_backfill(
        [_make_item("1"), _make_item("2"), _make_item("3")],
        dynamodb_client=None,
        bedrock_client=None,
        config=BackfillConfig(dry_run=True, limit=2),
        enrich_func=enrich_func,
        persist_func=persist_func,
    )

    assert summary.total_candidates == 2
    assert summary.processed == 2
    assert summary.planned_for_enrichment == 2
    assert summary.written == 0
    assert model_calls == []
    assert write_calls == []


def test_city_filter_limits_candidates_to_matching_pk() -> None:
    summary = run_backfill(
        [
            _make_item("1", PK="CITY#GANGNEUNG"),
            _make_item("2", PK="CITY#SEOUL"),
        ],
        dynamodb_client=None,
        bedrock_client=None,
        config=BackfillConfig(dry_run=True, city_pk="CITY#SEOUL"),
    )

    assert summary.total_candidates == 1
    assert summary.processed == 1
    assert summary.planned_for_enrichment == 1


def test_existing_succeeded_same_hash_is_skipped_without_write() -> None:
    item = _make_item("1")
    item["metadata_enrichment"] = {
        "status": "succeeded",
        "input_hash": compute_input_hash(item),
        "prompt_version": PROMPT_VERSION,
        "model_id": DEFAULT_MODEL_ID,
    }
    write_calls: list[str] = []

    def persist_func(*args: Any, **kwargs: Any) -> None:
        write_calls.append("called")

    summary = run_backfill(
        [item],
        dynamodb_client=None,
        bedrock_client=None,
        config=BackfillConfig(dry_run=False),
        persist_func=persist_func,
    )

    assert summary.total_candidates == 1
    assert summary.skipped == 1
    assert summary.unchanged == 1
    assert summary.written == 0
    assert write_calls == []


def test_three_consecutive_write_failures_stop_with_resume_cursor() -> None:
    write_calls: list[str] = []

    def persist_func(*args: Any, **kwargs: Any) -> None:
        write_calls.append("called")
        raise _client_error()

    summary = run_backfill(
        [_make_item("1"), _make_item("2"), _make_item("3"), _make_item("4")],
        dynamodb_client=None,
        bedrock_client=None,
        config=BackfillConfig(dry_run=False),
        enrich_func=lambda *args, **kwargs: _success_result(),
        persist_func=persist_func,
    )

    assert summary.processed == 3
    assert summary.failed == 3
    assert summary.stopped_after_consecutive_failures is True
    assert summary.resume_after == "ATTRACTION#3"
    assert len(write_calls) == 3
