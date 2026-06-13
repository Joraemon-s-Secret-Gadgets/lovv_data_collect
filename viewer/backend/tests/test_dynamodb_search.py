import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dynamodb_search import JsonFileRepository, SearchInputError, collect_columns, collect_indexes, decode_cursor, encode_cursor, query_index_items, search_items


FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "mock-data",
    "sample-items.json",
)


class DynamoDbSearchTests(unittest.TestCase):
    def setUp(self):
        self.repository = JsonFileRepository(FIXTURE_PATH)
        self.env = {
            "DYNAMODB_TABLE_NAME": "TourKoreaDomainData",
            "SCAN_PAGE_SIZE": "2",
            "MAX_SCAN_PAGES": "3",
        }

    def test_collect_columns_from_sample_items(self):
        result = collect_columns(self.repository, {"sampleSize": "10"}, self.env)

        self.assertEqual(result["tableName"], "TourKoreaDomainData")
        self.assertIn("PK", result["columns"])
        self.assertIn("city_name", result["columns"])
        self.assertIn("quality_status", result["columns"])

    def test_search_all_columns(self):
        result = search_items(self.repository, {"q": "안동", "limit": "10"}, self.env)

        self.assertEqual(result["count"], 3)
        self.assertFalse(result["scanLimitReached"])

    def test_search_selected_column(self):
        result = search_items(
            self.repository,
            {"q": "needs_review", "column": "quality_status", "limit": "10"},
            self.env,
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["entity_type"], "festival")

    def test_equals_mode(self):
        result = search_items(
            self.repository,
            {"q": "festival", "column": "entity_type", "mode": "equals", "limit": "10"},
            self.env,
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["title"], "안동국제탈춤페스티벌")

    def test_cursor_round_trip(self):
        cursor = encode_cursor({"offset": 2})

        self.assertEqual(decode_cursor(cursor), {"offset": 2})

    def test_limit_caps_result_count(self):
        result = search_items(self.repository, {"q": "KR", "limit": "1"}, self.env)

        self.assertEqual(result["count"], 1)
        self.assertIsNotNone(result["nextCursor"])

    def test_search_pagination_does_not_skip_items(self):
        first = search_items(self.repository, {"q": "KR", "limit": "1"}, self.env)
        second = search_items(
            self.repository,
            {"q": "KR", "limit": "1", "cursor": first["nextCursor"]},
            self.env,
        )

        self.assertEqual(first["items"][0]["SK"], "PROFILE")
        self.assertEqual(second["items"][0]["SK"], "ATTRACTION#126508")

    def test_collect_indexes_from_mock_repository(self):
        result = collect_indexes(self.repository, self.env)

        self.assertEqual(result["tableName"], "TourKoreaDomainData")
        self.assertEqual(result["indexes"][0]["indexName"], "GSI1")
        self.assertEqual(result["indexes"][0]["keySchema"][0]["attributeName"], "city_key")
        self.assertEqual(result["indexes"][1]["indexName"], "GSI2")
        self.assertEqual(result["indexes"][2]["indexName"], "GSI3")

    def test_query_index_by_partition_key(self):
        result = query_index_items(
            self.repository,
            {"indexName": "GSI1", "partitionValue": "CITY#Andong", "limit": "10"},
            self.env,
        )

        self.assertEqual(result["queryType"], "gsi")
        self.assertEqual(result["count"], 3)
        self.assertIn("city_name", result["columns"])

    def test_query_index_with_sort_key_condition(self):
        result = query_index_items(
            self.repository,
            {
                "indexName": "GSI1",
                "partitionValue": "CITY#Andong",
                "sortMode": "begins_with",
                "sortValue": "FESTIVAL#",
                "limit": "10",
            },
            self.env,
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["entity_type"], "festival")

    def test_query_index_rejects_unknown_index(self):
        with self.assertRaises(SearchInputError):
            query_index_items(
                self.repository,
                {"indexName": "UnknownIndex", "partitionValue": "CITY#Andong"},
                self.env,
            )


if __name__ == "__main__":
    unittest.main()
