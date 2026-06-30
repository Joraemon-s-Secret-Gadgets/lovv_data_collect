from kr_vector_index.preflight import build_preflight_summary


class FakeDynamoClient:
    def __init__(self, *, visitor_count: int = 2820, metadata_enrichment_count: int = 0) -> None:
        self.visitor_count = visitor_count
        self.metadata_enrichment_count = metadata_enrichment_count

    def query(self, **kwargs):
        entity_type = kwargs["ExpressionAttributeValues"][":entity_type"]["S"]
        counts = {
            "visitor_statistics": self.visitor_count,
            "attraction": 7024,
        }
        return {"Count": counts[entity_type]}

    def scan(self, **kwargs):
        names = kwargs.get("ExpressionAttributeNames") or {}
        if names.get("#target_attribute") == "metadata_enrichment":
            return {"Count": self.metadata_enrichment_count}
        return {"Count": 0}


def test_build_preflight_summary_marks_verified_visitor_and_non_enrichment_mode():
    client = FakeDynamoClient()

    summary = build_preflight_summary(
        client,
        table_name="TourKoreaDomainDataV2",
        entity_index_name="EntityTypeDomainIndex",
    )

    assert summary["visitor_statistics"]["coverage_ok"] is True
    assert summary["visitor_statistics"]["row_count"] == 2820
    assert summary["visitor_statistics"]["gsi_sk_count"] == 0
    assert summary["enrichment"]["attraction_count"] == 7024
    assert summary["enrichment"]["metadata_enrichment"] == 0
    assert summary["enrichment"]["mode"] == "non-enrichment-complete"


def test_build_preflight_summary_marks_bad_visitor_coverage():
    client = FakeDynamoClient(visitor_count=2819)

    summary = build_preflight_summary(
        client,
        table_name="TourKoreaDomainDataV2",
        entity_index_name="EntityTypeDomainIndex",
    )

    assert summary["visitor_statistics"]["coverage_ok"] is False
    assert summary["visitor_statistics"]["row_count"] == 2819


def test_build_preflight_summary_marks_enrichment_complete_when_rows_exist():
    client = FakeDynamoClient(metadata_enrichment_count=10)

    summary = build_preflight_summary(
        client,
        table_name="TourKoreaDomainDataV2",
        entity_index_name="EntityTypeDomainIndex",
    )

    assert summary["enrichment"]["metadata_enrichment"] == 10
    assert summary["enrichment"]["mode"] == "enrichment-complete"
