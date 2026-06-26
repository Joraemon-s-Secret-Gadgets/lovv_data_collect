"""Compare enrichment results between Nova Lite and OpenAI GPT-OSS-120B."""

import boto3
import json
import sys
sys.path.insert(0, "src")

from boto3.dynamodb.types import TypeDeserializer
from kr_details_pipeline.enrichment_engine import enrich_attraction, EnrichmentResult
from kr_details_pipeline.theme_classifier import classify_festival_theme, ThemeClassificationResult

SESSION = boto3.Session(profile_name="skn26_final", region_name="us-east-1")
MODELS = {
    "nova-lite": "amazon.nova-lite-v1:0",
    "gpt-oss-120b": "openai.gpt-oss-120b-1:0",
}


def get_sample_items(entity_prefix: str, limit: int = 3) -> list[dict]:
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
    return [{k: td.deserialize(v) for k, v in item.items()} for item in resp["Items"]]


def compare_attraction_enrichment():
    print("=" * 70)
    print("ATTRACTION ENRICHMENT: Nova Lite vs GPT-OSS-120B")
    print("=" * 70)

    bedrock = SESSION.client("bedrock-runtime")
    items = get_sample_items("ATTRACTION", limit=3)

    for item in items:
        print(f"\n{'─' * 70}")
        print(f"📍 {item['title']} (content_id: {item['content_id']})")
        print(f"   subtype: {item.get('attraction_subtype_name', 'N/A')}")
        print(f"   theme: {item.get('theme', 'N/A')}")
        print(f"   description: {(item.get('description') or '')[:80]}...")
        print()

        for model_name, model_id in MODELS.items():
            result: EnrichmentResult = enrich_attraction(bedrock, item, model_id=model_id)

            if result.status == "succeeded":
                print(f"  [{model_name}]")
                print(f"    indoor_outdoor:  {result.indoor_outdoor}")
                print(f"    vibe_tags:       {result.vibe_tags}")
                print(f"    experience_tags: {result.experience_tags}")
                print(f"    companion_fit:   {result.companion_fit}")
            else:
                print(f"  [{model_name}] FAILED: {result.metadata_enrichment.get('error_code')}")
            print()


def compare_festival_classification():
    print("\n" + "=" * 70)
    print("FESTIVAL CLASSIFICATION: Nova Lite vs GPT-OSS-120B")
    print("=" * 70)

    bedrock = SESSION.client("bedrock-runtime")
    items = get_sample_items("FESTIVAL", limit=2)

    for item in items:
        print(f"\n{'─' * 70}")
        print(f"🎉 {item['title']} (content_id: {item['content_id']})")
        print(f"   source_theme: {item.get('source_theme', 'N/A')}")
        print(f"   description: {(item.get('description') or '')[:80]}...")
        print()

        for model_name, model_id in MODELS.items():
            result: ThemeClassificationResult = classify_festival_theme(
                bedrock, item, model_id=model_id
            )

            if result.status == "succeeded":
                print(f"  [{model_name}]")
                print(f"    primary_theme: {result.primary_theme}")
                print(f"    theme_tags:    {result.theme_tags}")
            elif result.status == "review_required":
                print(f"  [{model_name}] REVIEW_REQUIRED (insufficient text)")
            else:
                print(f"  [{model_name}] FAILED: {result.festival_theme_classification.get('error_code')}")
            print()


if __name__ == "__main__":
    compare_attraction_enrichment()
    compare_festival_classification()
    print("\n✅ Comparison complete!")
