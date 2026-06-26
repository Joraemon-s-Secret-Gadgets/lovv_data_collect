"""Test Bedrock enrichment with real DynamoDB items (sample)."""

import boto3
import json
import sys
sys.path.insert(0, "src")

from boto3.dynamodb.types import TypeDeserializer
from kr_details_pipeline.enrichment_engine import enrich_attraction, EnrichmentResult
from kr_details_pipeline.theme_classifier import classify_festival_theme, ThemeClassificationResult

SESSION = boto3.Session(profile_name="skn26_final", region_name="us-east-1")

# Use Amazon Nova Lite (no use case registration required)
MODEL_ID = "amazon.nova-lite-v1:0"


def get_sample_items(entity_prefix: str, limit: int = 3) -> list[dict]:
    """Fetch sample items from DynamoDB."""
    ddb = SESSION.client("dynamodb")
    td = TypeDeserializer()

    resp = ddb.query(
        TableName="TourKoreaDomainData",
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": {"S": "CITY#Andong"},
            ":sk": {"S": f"{entity_prefix}#"},
        },
        Limit=limit,
    )

    items = []
    for ddb_item in resp["Items"]:
        item = {k: td.deserialize(v) for k, v in ddb_item.items()}
        items.append(item)
    return items


def test_attraction_enrichment():
    """Test enrichment on 3 real attraction items."""
    print("=" * 60)
    print("ATTRACTION ENRICHMENT TEST")
    print("=" * 60)

    bedrock = SESSION.client("bedrock-runtime")
    items = get_sample_items("ATTRACTION", limit=3)

    for item in items:
        print(f"\n--- {item['title']} (content_id: {item['content_id']}) ---")
        print(f"    subtype: {item.get('attraction_subtype_name', 'N/A')}")
        print(f"    theme: {item.get('theme', 'N/A')}")

        result: EnrichmentResult = enrich_attraction(bedrock, item, model_id=MODEL_ID)

        print(f"    STATUS: {result.status}")
        if result.status == "succeeded":
            print(f"    indoor_outdoor: {result.indoor_outdoor}")
            print(f"    vibe_tags: {result.vibe_tags}")
            print(f"    experience_tags: {result.experience_tags}")
            print(f"    companion_fit: {result.companion_fit}")
        elif result.status == "failed":
            print(f"    error: {result.metadata_enrichment.get('error_code')}")
        print()


def test_festival_classification():
    """Test theme classification on 2 real festival items."""
    print("=" * 60)
    print("FESTIVAL THEME CLASSIFICATION TEST")
    print("=" * 60)

    bedrock = SESSION.client("bedrock-runtime")
    items = get_sample_items("FESTIVAL", limit=2)

    for item in items:
        print(f"\n--- {item['title']} (content_id: {item['content_id']}) ---")
        print(f"    source_theme: {item.get('source_theme', 'N/A')}")
        print(f"    current theme: {item.get('theme', 'N/A')}")

        result: ThemeClassificationResult = classify_festival_theme(bedrock, item, model_id=MODEL_ID)

        print(f"    STATUS: {result.status}")
        if result.status == "succeeded":
            print(f"    primary_theme: {result.primary_theme}")
            print(f"    theme_tags: {result.theme_tags}")
        elif result.status == "failed":
            print(f"    error: {result.festival_theme_classification.get('error_code')}")
        elif result.status == "review_required":
            print(f"    (insufficient text for classification)")
        print()


if __name__ == "__main__":
    test_attraction_enrichment()
    test_festival_classification()
    print("\nDone!")
