#!/usr/bin/env python3
"""DynamoDB TourKoreaDomainData (V1) selective cleanup script.

Scans the V1 table and deletes all items whose province_key is NOT
KR-42 (강원도) or KR-47 (경상북도). Items belonging to these two
provinces are preserved.

Usage:
    # Dry-run (default): shows what would be deleted
    python scripts/cleanup_dynamodb_v1_non_target.py --profile skn26_final

    # Actually delete
    python scripts/cleanup_dynamodb_v1_non_target.py --profile skn26_final --execute
"""

import argparse
import sys
from collections import defaultdict

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "TourKoreaDomainData"
# province_key values to KEEP (강원도, 경상북도, and items without province_key attr)
KEEP_PROVINCES = {"PROVINCE#강원특별자치도", "PROVINCE#경상북도"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete non-강원/경북 items from TourKoreaDomainData (V1)."
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="AWS CLI profile name (default: environment/instance default)",
    )
    parser.add_argument(
        "--region",
        default="ap-northeast-2",
        help="AWS region (default: ap-northeast-2)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually delete items. Without this flag, runs in dry-run mode.",
    )
    return parser.parse_args()


def get_resource(profile: str | None, region: str):
    """Create a boto3 DynamoDB resource."""
    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    session = boto3.Session(**session_kwargs)
    return session.resource("dynamodb")


def scan_non_target_items(table) -> list[dict]:
    """Scan the table and return items NOT in KEEP_PROVINCES.

    Items without a province_key attribute are considered original
    강원/경북 data and are preserved.
    """
    items_to_delete = []
    scan_kwargs = {}

    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            # Items without province_key are original 강원/경북 data — keep them
            if "province_key" not in item:
                continue
            province = item["province_key"]
            if province not in KEEP_PROVINCES:
                items_to_delete.append({"PK": item["PK"], "SK": item["SK"], "province_key": province})

        # Handle pagination
        if "LastEvaluatedKey" in response:
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        else:
            break

    return items_to_delete


def delete_items_batch(table, items: list[dict]) -> int:
    """Delete items using batch_writer. Returns count of deleted items."""
    deleted = 0
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
            deleted += 1
    return deleted


def main() -> None:
    args = parse_args()
    dynamodb = get_resource(args.profile, args.region)
    table = dynamodb.Table(TABLE_NAME)

    print()
    print("=" * 60)
    print(f"  DynamoDB V1 Selective Cleanup: {TABLE_NAME}")
    print(f"  Region:  {args.region}")
    print(f"  Profile: {args.profile or '(default)'}")
    print(f"  Mode:    {'EXECUTE (DESTRUCTIVE)' if args.execute else 'DRY-RUN'}")
    print(f"  Keep:    {', '.join(sorted(KEEP_PROVINCES))} + items without province_key")
    print("=" * 60)
    print()

    # Scan for items to delete
    print("[SCAN] Scanning table for non-target province items...")
    items_to_delete = scan_non_target_items(table)

    # Summary by province
    province_counts: dict[str, int] = defaultdict(int)
    for item in items_to_delete:
        province_counts[item.get("province_key", "(none)")] += 1

    if not items_to_delete:
        print("[DONE] No items to delete. Table already contains only target provinces.")
        return

    print(f"\n[RESULT] Found {len(items_to_delete)} items to delete:")
    for province, count in sorted(province_counts.items()):
        print(f"  - {province}: {count} items")
    print()

    if not args.execute:
        print("[DRY-RUN] No items were deleted. Use --execute to perform deletion.")
        return

    # Safety confirmation
    confirm = input(
        f"  Delete {len(items_to_delete)} items? This is IRREVERSIBLE. (y/N): "
    ).strip().lower()
    if confirm != "y":
        print("\n  Aborted. No changes were made.")
        sys.exit(0)

    # Perform deletion
    print(f"\n[DELETE] Deleting {len(items_to_delete)} items...")
    deleted = delete_items_batch(table, items_to_delete)
    print(f"[DONE] Successfully deleted {deleted} items.")

    # Verify remaining items
    print("\n[VERIFY] Scanning to confirm remaining items...")
    scan_response = table.scan(Select="COUNT")
    remaining = scan_response["Count"]
    print(f"[VERIFY] Remaining items in table: {remaining}")
    print()


if __name__ == "__main__":
    main()
