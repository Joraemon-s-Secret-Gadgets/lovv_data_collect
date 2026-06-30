"""Tests for the KR domain loader Lambda handler."""

from __future__ import annotations

import io
import json
import sys
import types

import pytest

from kr_details_pipeline.handlers import domain_loader_handler


class FakeS3Client:
    def __init__(self, payload: dict, objects: dict[str, object] | None = None) -> None:
        self.payload = payload
        self.objects = objects or {}
        self.put_calls: list[dict] = []

    def get_object(self, **kwargs):  # noqa: ANN001
        payload = self.objects.get(str(kwargs.get("Key") or ""), self.payload)
        if isinstance(payload, bytes):
            body = payload
        else:
            body = json.dumps(payload).encode("utf-8")
        return {"Body": io.BytesIO(body)}

    def put_object(self, **kwargs):  # noqa: ANN001
        self.put_calls.append(kwargs)
        return {}


class FakeDynamoClient:
    pass


class FakeBoto3:
    def __init__(self, s3: FakeS3Client, ddb: FakeDynamoClient | None = None) -> None:
        self.s3 = s3
        self.ddb = ddb

    def client(self, service_name: str):  # noqa: ANN201
        if service_name == "s3":
            return self.s3
        if service_name == "dynamodb":
            if self.ddb is None:
                raise AssertionError("preprocessing handler must not create a DynamoDB client")
            return self.ddb
        raise ValueError(service_name)


def _payload() -> dict:
    return {
        "meta": {
            "city_name_en": "Andong",
            "city_name_ko": "안동시",
            "province": "경상북도",
            "lDongRegnCd": "47",
            "lDongSignguCd": "170",
        },
        "attractions": [
            {
                "contentid": "100",
                "contenttypeid": "12",
                "title": "하회마을",
                "mapx": "128.6",
                "mapy": "36.5",
                "_assigned_theme": "history",
            }
        ],
    }


def _passed_image_payload() -> dict:
    payload = _payload()
    payload["attractions"][0]["firstimage"] = "https://cdn.example.com/andong.jpg"
    payload["attractions"][0]["detail"] = {
        "common": {
            "lclsSystm3": "NA010100",
        }
    }
    return payload


def test_handler_writes_failed_records_to_failed_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload()
    payload["attractions"][0].pop("title")
    s3 = FakeS3Client(payload)
    fake_boto3 = FakeBoto3(s3)
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=fake_boto3.client))

    response = domain_loader_handler.handler(
        {
            "bucket": "bucket",
            "raw_key": "raw/KR/details/20260629/ANDONG.json",
            "table_name": "TourKoreaDomainDataV2",
            "processed_prefix": "processed/KR/details",
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["status"] == "partial"
    assert response["summary"]["passed_items"] == 1
    assert response["summary"]["failed_items"] == 1

    failed_call = next(call for call in s3.put_calls if call["Key"].endswith("/failed/ANDONG.json"))
    failed_payload = json.loads(failed_call["Body"])
    assert failed_payload["records"][0]["entity_id"] == "ATT-100"
    assert failed_payload["records"][0]["quality_status"] == "failed"


def test_handler_writes_processed_outputs_without_dynamodb(monkeypatch: pytest.MonkeyPatch) -> None:
    s3 = FakeS3Client(_payload())
    fake_boto3 = FakeBoto3(s3)
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=fake_boto3.client))

    response = domain_loader_handler.handler(
        {
            "bucket": "bucket",
            "raw_key": "raw/KR/details/20260629/ANDONG.json",
            "table_name": "TourKoreaDomainDataV2",
            "processed_prefix": "processed/KR/details",
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["status"] == "ok"
    assert response["summary"]["passed_items"] == 1
    assert response["summary"]["review_items"] == 1
    assert response["summary"]["failed_items"] == 0

    put_keys = {call["Key"] for call in s3.put_calls}
    assert put_keys == {
        "processed/KR/details/20260629/passed/ANDONG.json",
        "processed/KR/details/20260629/review/ANDONG.json",
        "processed/KR/details/20260629/failed/ANDONG.json",
        "processed/KR/details/20260629/quality/ANDONG.json",
    }

    passed_call = next(call for call in s3.put_calls if call["Key"].endswith("/passed/ANDONG.json"))
    passed_payload = json.loads(passed_call["Body"])
    assert len(passed_payload["records"]) == 1
    assert passed_payload["records"][0]["entity_type"] == "city_metadata"
    assert passed_payload["records"][0]["PK"] == passed_payload["records"][0]["city_key"]


def test_handler_extracts_s3_event_record(monkeypatch: pytest.MonkeyPatch) -> None:
    s3 = FakeS3Client(_payload())
    fake_boto3 = FakeBoto3(s3)
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=fake_boto3.client))

    response = domain_loader_handler.handler(
        {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "bucket"},
                        "object": {"key": "raw/KR/details/20260609/Andong.json"},
                    }
                }
            ],
            "table_name": "TourKoreaDomainData",
            "write_processed": False,
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["raw_key"] == "raw/KR/details/20260609/Andong.json"
    assert response["summary"]["passed_items"] == 1
    assert s3.put_calls == []


def test_handler_enriches_wikipedia_and_rewrites_image_url(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_payload = _passed_image_payload()
    wiki_payload = [
        {
            "source_name": "Wikipedia",
            "source_url": "https://ko.wikipedia.org/wiki/안동시",
            "city_id": "KR-47-ANDONG",
            "city_name_ko": "안동시",
            "city_name_en": "ANDONG",
            "province": "경상북도",
            "description": "안동시는 경상북도 북부의 도시이다.",
            "geography_description": "낙동강 유역에 위치한다.",
            "site_urls": ["https://www.andong.go.kr"],
        }
    ]
    s3 = FakeS3Client(
        raw_payload,
        objects={"raw/KR/wikipedia/20260629/cities.json": wiki_payload},
    )
    fake_boto3 = FakeBoto3(s3)
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=fake_boto3.client))
    monkeypatch.setattr("kr_image_processor.processor.fetch_bytes", lambda url, timeout=30: b"image-bytes")

    response = domain_loader_handler.handler(
        {
            "bucket": "bucket",
            "raw_key": "raw/KR/details/20260629/ANDONG.json",
            "table_name": "TourKoreaDomainDataV2",
            "processed_prefix": "processed/KR/details",
            "image_bucket": "image-bucket",
        },
        context=None,
    )

    assert response["statusCode"] == 200
    assert response["summary"]["wiki"]["status"] == "matched"
    assert response["summary"]["images"]["images_downloaded"] == 1

    passed_call = next(call for call in s3.put_calls if call["Key"].endswith("/passed/ANDONG.json"))
    passed_payload = json.loads(passed_call["Body"])
    city_record = next(record for record in passed_payload["records"] if record["entity_type"] == "city_metadata")
    attraction_record = next(record for record in passed_payload["records"] if record["entity_type"] == "attraction")

    assert city_record["wiki_status"] == "matched"
    assert city_record["source_url"] == "https://ko.wikipedia.org/wiki/안동시"
    assert city_record["description"] == "안동시는 경상북도 북부의 도시이다."
    assert city_record["site_urls"] == ["https://www.andong.go.kr"]

    assert attraction_record["source_image_url"] == "https://cdn.example.com/andong.jpg"
    assert attraction_record["image_url"].startswith("https://image-bucket.s3.amazonaws.com/images/KR/Andong/")
    assert attraction_record["image_s3_key"].startswith("images/KR/Andong/")
    assert attraction_record["image_status"] == "ok"

    image_put = next(call for call in s3.put_calls if call["Bucket"] == "image-bucket")
    assert image_put["Body"] == b"image-bytes"
