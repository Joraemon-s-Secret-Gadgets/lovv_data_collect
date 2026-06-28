"""Tests for KR load helpers."""

from __future__ import annotations

import unittest

from boto3.dynamodb.types import TypeDeserializer

from kr_details_pipeline import load


class FakeDynamoClient:
    def __init__(self) -> None:
        self.put_calls: list[dict] = []

    def put_item(self, **kwargs):  # noqa: ANN001
        self.put_calls.append(kwargs)
        return {"ConsumedCapacity": {"CapacityUnits": 1}}


class LoadTest(unittest.TestCase):
    def test_load_passed_records_writes_city_and_entities(self) -> None:
        payload = {
            "status": "passed",
            "city_record": {
                "city_id": "KR-47-001",
                "city_name_en": "ANDONG",
                "city_name_ko": "안동시",
                "province": "경북",
                "lDongRegnCd": "47",
                "lDongSignguCd": "001",
            },
            "records": [
                {
                    "entity_type": "attraction",
                    "entity_id": "ATT-1001",
                    "content_id": "1001",
                    "SK": "ATTRACTION#1001",
                    "quality_status": "passed",
                },
                {
                    "entity_type": "visitor_statistics",
                    "entity_id": "KR-STAT-KR-47-001-202601",
                    "month": "202601",
                    "SK": "STAT#202601",
                    "quality_status": "passed",
                },
            ],
        }
        fake_client = FakeDynamoClient()
        result = load.load_processed_payload(payload, "TourKoreaDomainData", fake_client)

        self.assertEqual(3, result.passed)
        self.assertEqual(0, result.failed)
        self.assertEqual(3, len(fake_client.put_calls))

    def test_visitor_statistics_uses_stat_sort_key_without_festival_gsi(self) -> None:
        payload = {
            "status": "passed",
            "city_record": {
                "city_id": "KR-47-001",
                "city_name_en": "ANDONG",
                "city_name_ko": "안동시",
                "province": "경북",
            },
            "records": [
                {
                    "entity_type": "visitor_statistics",
                    "entity_id": "KR-STAT-KR-47-001-202601",
                    "month": "202601",
                    "quality_status": "passed",
                },
            ],
        }
        fake_client = FakeDynamoClient()

        load.load_processed_payload(payload, "TourKoreaDomainDataV2", fake_client)

        deserializer = TypeDeserializer()
        raw_item = fake_client.put_calls[1]["Item"]
        item = {key: deserializer.deserialize(value) for key, value in raw_item.items()}
        self.assertEqual("STAT#202601", item["SK"])
        self.assertEqual("STAT#202601", item["domain_sort_key"])
        self.assertEqual("PROVINCE#경북", item["province_key"])
        self.assertNotIn("gsi_sk", item)

    def test_write_item_repairs_visitor_statistics_fallback_keys(self) -> None:
        fake_client = FakeDynamoClient()

        load._write_item(
            fake_client,
            "TourKoreaDomainDataV2",
            {
                "PK": "CITY#ANDONG",
                "SK": "STAT#202601",
                "entity_type": "visitor_statistics",
                "entity_id": "KR-STAT-KR-47-001-202601",
                "month": "202601",
                "province": "경북",
                "province_key": "UNKNOWN",
                "domain_sort_key": "visitor_statistics#KR-STAT-KR-47-001-202601",
                "gsi_sk": "visitor_statistics#KR-STAT-KR-47-001-202601",
            },
        )

        deserializer = TypeDeserializer()
        raw_item = fake_client.put_calls[0]["Item"]
        item = {key: deserializer.deserialize(value) for key, value in raw_item.items()}
        self.assertEqual("STAT#202601", item["domain_sort_key"])
        self.assertEqual("PROVINCE#경북", item["province_key"])
        self.assertNotIn("gsi_sk", item)


if __name__ == "__main__":
    unittest.main()
