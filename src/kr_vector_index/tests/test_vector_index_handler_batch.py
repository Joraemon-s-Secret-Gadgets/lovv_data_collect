import json
import sys
import types

from kr_vector_index.handlers import vector_index_handler
from kr_vector_index.tests.test_vector_index_handler import FakeBoto3


def test_handler_plan_creates_small_city_offset_batches(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=FakeBoto3().client)
    )
    monkeypatch.setattr(
        vector_index_handler,
        "export_items",
        lambda client, table_name, city_pk=None, index_name="EntityTypeDomainIndex": [
            {"PK": "CITY#A", "SK": "ATTRACTION#1", "entity_type": "attraction"},
            {"PK": "CITY#A", "SK": "ATTRACTION#2", "entity_type": "attraction"},
            {"PK": "CITY#A", "SK": "FESTIVAL#1", "entity_type": "festival"},
            {"PK": "CITY#B", "SK": "ATTRACTION#3", "entity_type": "attraction"},
        ],
    )

    response = vector_index_handler.handler(
        {
            "command": "plan",
            "batch_size": 2,
            "enrichment_mode": "non-enrichment-complete",
            "visitor_statistics_coverage_ok": True,
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["batch_count"] == 3
    assert response["summary"]["item_count"] == 4
    assert response["summary"]["enrichment_mode"] == "non-enrichment-complete"
    assert response["summary"]["visitor_statistics_coverage_ok"] is True
    assert response["batches"] == [
        {
            "batch_id": "kr-vector-000001",
            "city_pk": "CITY#A",
            "start_offset": 0,
            "max_items": 2,
            "table_name": "TourKoreaDomainDataV2",
            "entity_index_name": "EntityTypeDomainIndex",
            "vector_bucket": "lovv-vector-dev",
            "index_name": "kr-tour-domain-v2",
        },
        {
            "batch_id": "kr-vector-000002",
            "city_pk": "CITY#A",
            "start_offset": 2,
            "max_items": 2,
            "table_name": "TourKoreaDomainDataV2",
            "entity_index_name": "EntityTypeDomainIndex",
            "vector_bucket": "lovv-vector-dev",
            "index_name": "kr-tour-domain-v2",
        },
        {
            "batch_id": "kr-vector-000003",
            "city_pk": "CITY#B",
            "start_offset": 0,
            "max_items": 2,
            "table_name": "TourKoreaDomainDataV2",
            "entity_index_name": "EntityTypeDomainIndex",
            "vector_bucket": "lovv-vector-dev",
            "index_name": "kr-tour-domain-v2",
        },
    ]


def test_handler_worker_processes_one_bounded_batch(monkeypatch):
    fake_boto3 = FakeBoto3()
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=fake_boto3.client)
    )
    monkeypatch.setattr(
        vector_index_handler,
        "fetch_vectorizable_items_by_pk",
        lambda client, table_name, city_pk: [
            {
                "PK": city_pk,
                "SK": "ATTRACTION#1",
                "entity_type": "attraction",
                "content_id": "1",
                "city_id": "KR-A",
                "city_name_en": "A",
                "title": "first",
                "quality_status": "passed",
            },
            {
                "PK": city_pk,
                "SK": "ATTRACTION#2",
                "entity_type": "attraction",
                "content_id": "2",
                "city_id": "KR-A",
                "city_name_en": "A",
                "title": "second",
                "quality_status": "passed",
            },
        ],
    )
    monkeypatch.setattr(
        vector_index_handler, "embed_chunks", lambda client, chunks: [[0.1, 0.2]]
    )
    monkeypatch.setattr(
        vector_index_handler,
        "put_vectors_sdk",
        lambda client, records, vector_bucket, index_name: len(records),
    )

    response = vector_index_handler.handler(
        {
            "command": "worker",
            "batch": {
                "batch_id": "kr-vector-000001",
                "city_pk": "CITY#A",
                "start_offset": 1,
                "max_items": 1,
                "table_name": "TourKoreaDomainDataV2",
                "vector_bucket": "lovv-vector-dev",
                "index_name": "kr-tour-domain-v2",
            },
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["batch_id"] == "kr-vector-000001"
    assert response["summary"]["item_count"] == 1
    assert response["summary"]["chunk_count"] == 1
    assert response["summary"]["vector_success_count"] == 1


def test_handler_aggregate_preserves_failed_batch_ids(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=FakeBoto3().client)
    )

    response = vector_index_handler.handler(
        {
            "command": "aggregate",
            "batch_results": [
                {
                    "summary": {
                        "batch_id": "kr-vector-000001",
                        "item_count": 2,
                        "chunk_count": 2,
                        "vector_success_count": 2,
                        "failed_count": 0,
                    }
                },
                {
                    "summary": {
                        "batch_id": "kr-vector-000002",
                        "item_count": 1,
                        "chunk_count": 1,
                        "vector_success_count": 0,
                        "failed_count": 1,
                    }
                },
            ],
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["batch_count"] == 2
    assert response["summary"]["item_count"] == 3
    assert response["summary"]["chunk_count"] == 3
    assert response["summary"]["vector_success_count"] == 2
    assert response["summary"]["status"] == "partial"
    assert response["summary"]["failed_count"] == 1
    assert response["summary"]["failed_batch_count"] == 1
    assert response["summary"]["failed_batch_ids"] == ["kr-vector-000002"]


def test_handler_aggregate_writes_manifest_when_bucket_configured(monkeypatch):
    fake_boto3 = FakeBoto3()
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=fake_boto3.client)
    )
    monkeypatch.setenv("MANIFEST_BUCKET", "lovv-data-pipeline-dev-123")

    response = vector_index_handler.handler(
        {
            "command": "aggregate",
            "entity_counts": {"attraction": 2},
            "batch_results": [
                {
                    "summary": {
                        "batch_id": "kr-vector-000001",
                        "item_count": 2,
                        "chunk_count": 2,
                        "vector_success_count": 2,
                        "failed_count": 0,
                    }
                }
            ],
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["status"] == "succeeded"
    assert (
        response["summary"]["manifest_s3_uri"]
        == "s3://lovv-data-pipeline-dev-123/processed/KR/vector/manifests/latest.json"
    )
    body = json.loads(fake_boto3.s3.objects[0]["Body"].decode("utf-8"))
    assert body["status"] == "succeeded"
    assert body["entity_counts"] == {"attraction": 2}
    assert body["batch_count"] == 1
    assert body["failed_batch_ids"] == []


def test_handler_preflight_returns_visitor_and_enrichment_gates(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=FakeBoto3().client)
    )
    monkeypatch.setattr(
        vector_index_handler,
        "build_preflight_summary",
        lambda client, table_name, entity_index_name: {
            "visitor_statistics": {"coverage_ok": True, "row_count": 2820},
            "enrichment": {"metadata_enrichment": 0, "mode": "non-enrichment-complete"},
        },
    )

    response = vector_index_handler.handler({"command": "preflight"}, context=None)

    assert response["statusCode"] == 200
    assert response["summary"]["command"] == "preflight"
    assert response["summary"]["visitor_statistics"]["coverage_ok"] is True
    assert response["summary"]["enrichment"]["mode"] == "non-enrichment-complete"
