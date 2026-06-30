import sys
import types

from kr_vector_index.handlers import vector_index_handler


class FakeDynamoClient:
    pass


class FakeBedrockClient:
    pass


class FakeS3VectorsClient:
    pass


class FakeS3Client:
    def __init__(self) -> None:
        self.objects = []

    def put_object(self, **kwargs):
        self.objects.append(kwargs)


class FakeBoto3:
    def __init__(self) -> None:
        self.s3 = FakeS3Client()

    def client(self, service_name: str):  # noqa: ANN201
        if service_name == "dynamodb":
            return FakeDynamoClient()
        if service_name == "bedrock-runtime":
            return FakeBedrockClient()
        if service_name == "s3vectors":
            return FakeS3VectorsClient()
        if service_name == "s3":
            return self.s3
        raise ValueError(service_name)


def test_handler_returns_export_counts(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=FakeBoto3().client)
    )
    monkeypatch.setattr(
        vector_index_handler,
        "export_items",
        lambda client, table_name, city_pk=None, index_name="EntityTypeDomainIndex": [
            {"entity_type": "attraction"},
            {"entity_type": "attraction"},
            {"entity_type": "festival"},
        ],
    )

    response = vector_index_handler.handler({"command": "export-counts"}, context=None)

    assert response["statusCode"] == 200
    assert response["summary"]["entity_counts"] == {"attraction": 2, "festival": 1}
    assert response["summary"]["item_count"] == 3


def test_handler_uses_v2_entity_type_index_by_default(monkeypatch):
    calls = []

    def export_items(client, table_name, city_pk=None, index_name="GSI3"):
        calls.append(
            {
                "table_name": table_name,
                "city_pk": city_pk,
                "index_name": index_name,
            }
        )
        return []

    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=FakeBoto3().client)
    )
    monkeypatch.setattr(vector_index_handler, "export_items", export_items)

    response = vector_index_handler.handler({"command": "export-counts"}, context=None)

    assert response["statusCode"] == 200
    assert calls == [
        {
            "table_name": "TourKoreaDomainDataV2",
            "city_pk": None,
            "index_name": "EntityTypeDomainIndex",
        }
    ]


def test_handler_dry_run_builds_chunks_without_upsert(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=FakeBoto3().client)
    )
    monkeypatch.setattr(
        vector_index_handler,
        "export_items",
        lambda client, table_name, city_pk=None, index_name="EntityTypeDomainIndex": [
            {
                "PK": "CITY#Andong",
                "SK": "ATTRACTION#100",
                "entity_type": "attraction",
                "content_id": "100",
                "city_id": "KR-Andong",
                "city_name_en": "Andong",
                "title": "하회마을",
                "address": "경상북도 안동시",
                "quality_status": "passed",
            }
        ],
    )

    response = vector_index_handler.handler(
        {"command": "build", "dry_run": True}, context=None
    )

    assert response["statusCode"] == 200
    assert response["summary"]["chunk_count"] == 1
    assert response["summary"]["vector_success_count"] == 0


def test_handler_worker_dry_run_does_not_call_bedrock_or_s3vectors(monkeypatch):
    # Given: one vectorizable worker batch and a client factory that blocks write clients.
    def client(service_name: str):  # noqa: ANN202
        if service_name == "dynamodb":
            return FakeDynamoClient()
        raise AssertionError(f"unexpected write client: {service_name}")

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    monkeypatch.setattr(
        vector_index_handler,
        "fetch_vectorizable_items_by_pk",
        lambda client, table_name, city_pk: [
            {
                "PK": city_pk,
                "SK": "ATTRACTION#100",
                "entity_type": "attraction",
                "content_id": "100",
                "city_id": "KR-Andong",
                "city_name_en": "Andong",
                "title": "하회마을",
                "quality_status": "passed",
            }
        ],
    )

    # When: the worker smoke command is invoked in dry-run mode.
    response = vector_index_handler.handler(
        {
            "command": "worker",
            "dry_run": True,
            "batch": {
                "batch_id": "kr-vector-000001",
                "city_pk": "CITY#Andong",
                "start_offset": 0,
                "max_items": 1,
            },
        },
        context=None,
    )

    # Then: the worker returns bounded counts without Bedrock or S3 Vector writes.
    assert response["statusCode"] == 200
    assert response["summary"]["item_count"] == 1
    assert response["summary"]["chunk_count"] == 1
    assert response["summary"]["vector_success_count"] == 0


def test_handler_build_embeds_and_upserts_when_not_dry_run(monkeypatch):
    fake_boto3 = FakeBoto3()
    monkeypatch.setitem(
        sys.modules, "boto3", types.SimpleNamespace(client=fake_boto3.client)
    )
    monkeypatch.setenv("MANIFEST_BUCKET", "lovv-data-pipeline-dev-123")
    monkeypatch.setattr(
        vector_index_handler,
        "export_items",
        lambda client, table_name, city_pk=None, index_name="EntityTypeDomainIndex": [
            {
                "PK": "CITY#Andong",
                "SK": "ATTRACTION#100",
                "entity_type": "attraction",
                "content_id": "100",
                "city_id": "KR-Andong",
                "city_name_en": "Andong",
                "title": "하회마을",
                "address": "경상북도 안동시",
                "quality_status": "passed",
            }
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
        {"command": "build", "dry_run": False, "max_items": 1}, context=None
    )

    assert response["statusCode"] == 200
    assert response["summary"]["dry_run"] is False
    assert response["summary"]["chunk_count"] == 1
    assert response["summary"]["vector_success_count"] == 1
    assert (
        response["summary"]["manifest_s3_uri"]
        == "s3://lovv-data-pipeline-dev-123/processed/KR/vector/manifests/latest.json"
    )
    assert fake_boto3.s3.objects[0]["Bucket"] == "lovv-data-pipeline-dev-123"
