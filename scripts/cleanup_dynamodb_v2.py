#!/usr/bin/env python3
"""DynamoDB TourKoreaDomainDataV2 table cleanup script.

Deletes and recreates the TourKoreaDomainDataV2 table to start from an
empty state before a full pipeline execution. Preserves the exact schema
(PK, SK, 4 GSIs) and settings (PAY_PER_REQUEST, PITR enabled).

Requirements: 9.8, 9.9
"""

import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "TourKoreaDomainDataV2"

# Table schema definition (mirrors Terraform main.tf)
TABLE_SCHEMA = {
    "TableName": TABLE_NAME,
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},
        {"AttributeName": "SK", "KeyType": "RANGE"},
    ],
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": "entity_type", "AttributeType": "S"},
        {"AttributeName": "city_key", "AttributeType": "S"},
        {"AttributeName": "province_key", "AttributeType": "S"},
        {"AttributeName": "domain_sort_key", "AttributeType": "S"},
        {"AttributeName": "gsi_sk", "AttributeType": "S"},
    ],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": "CityDomainIndex",
            "KeySchema": [
                {"AttributeName": "city_key", "KeyType": "HASH"},
                {"AttributeName": "domain_sort_key", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
        {
            "IndexName": "ProvinceDomainIndex",
            "KeySchema": [
                {"AttributeName": "province_key", "KeyType": "HASH"},
                {"AttributeName": "domain_sort_key", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
        {
            "IndexName": "EntityTypeDomainIndex",
            "KeySchema": [
                {"AttributeName": "entity_type", "KeyType": "HASH"},
                {"AttributeName": "domain_sort_key", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
        {
            "IndexName": "FestivalMonthIndex",
            "KeySchema": [
                {"AttributeName": "entity_type", "KeyType": "HASH"},
                {"AttributeName": "gsi_sk", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
    ],
    "BillingMode": "PAY_PER_REQUEST",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete and recreate TourKoreaDomainDataV2 DynamoDB table."
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
    return parser.parse_args()


def get_client(profile: str | None, region: str):
    """Create a boto3 DynamoDB client with optional profile."""
    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    session = boto3.Session(**session_kwargs)
    return session.client("dynamodb")


def table_exists(client, table_name: str) -> bool:
    """Check if a DynamoDB table exists."""
    try:
        resp = client.describe_table(TableName=table_name)
        return resp["Table"]["TableStatus"] in ("ACTIVE", "CREATING", "UPDATING")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def delete_table(client, table_name: str) -> None:
    """Delete the table and wait until deletion completes."""
    print(f"[DELETE] Deleting table '{table_name}'...")
    client.delete_table(TableName=table_name)

    print("[DELETE] Waiting for table deletion to complete...")
    waiter = client.get_waiter("table_not_exists")
    waiter.wait(
        TableName=table_name,
        WaiterConfig={"Delay": 5, "MaxAttempts": 60},
    )
    print(f"[DELETE] Table '{table_name}' deleted successfully.")


def create_table(client, schema: dict) -> None:
    """Create the table and wait until it becomes ACTIVE."""
    table_name = schema["TableName"]
    print(f"[CREATE] Creating table '{table_name}'...")
    client.create_table(**schema)

    print("[CREATE] Waiting for table to become ACTIVE...")
    waiter = client.get_waiter("table_exists")
    waiter.wait(
        TableName=table_name,
        WaiterConfig={"Delay": 5, "MaxAttempts": 60},
    )
    print(f"[CREATE] Table '{table_name}' is now ACTIVE.")


def enable_pitr(client, table_name: str) -> None:
    """Enable Point-in-Time Recovery on the table."""
    print("[PITR] Enabling Point-in-Time Recovery...")
    client.update_continuous_backups(
        TableName=table_name,
        PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True},
    )
    print("[PITR] Point-in-Time Recovery enabled.")


def confirm_empty_state(client, table_name: str) -> None:
    """Print confirmation that the table is empty."""
    resp = client.describe_table(TableName=table_name)
    item_count = resp["Table"]["ItemCount"]
    table_status = resp["Table"]["TableStatus"]
    gsi_count = len(resp["Table"].get("GlobalSecondaryIndexes", []))

    print()
    print("=" * 60)
    print(f"  Table:       {table_name}")
    print(f"  Status:      {table_status}")
    print(f"  Item Count:  {item_count}")
    print(f"  GSIs:        {gsi_count}")
    print(f"  Billing:     PAY_PER_REQUEST")
    print(f"  PITR:        Enabled")
    print("=" * 60)
    print()
    print("[DONE] Table is ready in empty state for pipeline execution.")


def main() -> None:
    args = parse_args()
    client = get_client(args.profile, args.region)

    print()
    print("=" * 60)
    print(f"  DynamoDB Table Cleanup: {TABLE_NAME}")
    print(f"  Region:  {args.region}")
    print(f"  Profile: {args.profile or '(default)'}")
    print("=" * 60)
    print()
    print("  WARNING: This will DELETE all data in the table and")
    print("  recreate it from scratch. This action is IRREVERSIBLE.")
    print()

    # Safety confirmation prompt
    confirm = input("  Are you sure you want to proceed? (y/N): ").strip().lower()
    if confirm != "y":
        print("\n  Aborted. No changes were made.")
        sys.exit(0)

    print()

    # Check if table exists
    if table_exists(client, TABLE_NAME):
        delete_table(client, TABLE_NAME)
    else:
        print(f"[SKIP] Table '{TABLE_NAME}' does not exist. Skipping deletion.")

    # Small delay between delete and create to avoid race conditions
    time.sleep(2)

    # Recreate table
    create_table(client, TABLE_SCHEMA)

    # Enable Point-in-Time Recovery (not available in CreateTable API)
    enable_pitr(client, TABLE_NAME)

    # Print final confirmation
    confirm_empty_state(client, TABLE_NAME)


if __name__ == "__main__":
    main()
