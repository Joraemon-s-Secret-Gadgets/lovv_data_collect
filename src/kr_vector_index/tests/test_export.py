from kr_vector_index.export import export_items, should_vectorize


def test_should_vectorize_excludes_visitor_statistics() -> None:
    assert should_vectorize({"entity_type": "visitor_statistics", "quality_status": "passed"}) is False


def test_should_vectorize_requires_passed_quality() -> None:
    assert should_vectorize({"entity_type": "attraction", "quality_status": "review"}) is False
    assert should_vectorize({"entity_type": "attraction", "quality_status": "passed"}) is True


def test_export_items_default_entity_types_exclude_visitor_statistics() -> None:
    client = RecordingDynamoClient()

    items = export_items(client, table_name="TourKoreaDomainDataV2")

    assert items == []
    assert "visitor_statistics" not in client.queried_entity_types


class RecordingDynamoClient:
    def __init__(self) -> None:
        self.queried_entity_types: list[str] = []

    def query(self, **kwargs):
        expression_values = kwargs["ExpressionAttributeValues"]
        entity_type = expression_values[":entity_type"]["S"]
        self.queried_entity_types.append(str(entity_type))
        return {"Items": []}
