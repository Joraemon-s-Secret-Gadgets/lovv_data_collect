from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from kr_details_pipeline.visitor_statistics_backfill import (
    BackfillInputs,
    build_backfill_plan,
)

DEFAULT_BUCKET: Final = "lovv-data-pipeline-dev-925273580929"
DEFAULT_CITY_LOOKUP_PATH: Final = Path("data/KR/city_name_en_lookup.json")
DEFAULT_INDEX_NAME: Final = "EntityTypeDomainIndex"
DEFAULT_PROFILE: Final = "skn26_final"
DEFAULT_RAW_KEY: Final = "raw/KR/datalab/20260629/visitor_statistics_2025.json"
DEFAULT_REGION: Final = "us-east-1"
DEFAULT_STATS_PATH: Final = Path("data/KR/visitor_statistics_2025.json")
DEFAULT_TABLE_NAME: Final = "TourKoreaDomainDataV2"


@dataclass(frozen=True, slots=True)
class BackfillConfig:
    table_name: str
    index_name: str
    region: str
    profile: str | None
    stats_path: Path
    city_lookup_path: Path
    raw_bucket: str
    raw_key: str
    limit: int | None
    apply: bool
    upload_raw: bool


def parse_args() -> BackfillConfig:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table-name", default=DEFAULT_TABLE_NAME)
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--stats-path", type=Path, default=DEFAULT_STATS_PATH)
    parser.add_argument(
        "--city-lookup-path", type=Path, default=DEFAULT_CITY_LOOKUP_PATH
    )
    parser.add_argument("--raw-bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--raw-key", default=DEFAULT_RAW_KEY)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--upload-raw", action="store_true")
    args = parser.parse_args()
    return BackfillConfig(
        table_name=args.table_name,
        index_name=args.index_name,
        region=args.region,
        profile=args.profile or None,
        stats_path=args.stats_path,
        city_lookup_path=args.city_lookup_path,
        raw_bucket=args.raw_bucket,
        raw_key=args.raw_key,
        limit=args.limit,
        apply=args.apply,
        upload_raw=args.upload_raw,
    )


def main() -> int:
    config = parse_args()
    session = boto3.Session(profile_name=config.profile, region_name=config.region)
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(config.table_name)

    city_items = _query_entity(table, config.index_name, "city_metadata")
    existing_stats = _query_entity(table, config.index_name, "visitor_statistics")
    datalab_records = _read_json_mapping(config.stats_path)
    city_lookup = _read_string_mapping(config.city_lookup_path)
    plan = build_backfill_plan(
        BackfillInputs(
            city_metadata_items=city_items,
            existing_statistics_items=existing_stats,
            datalab_records=datalab_records,
            city_name_lookup=city_lookup,
            source_key=config.raw_key,
        )
    )
    planned_items = plan.items[: config.limit] if config.limit else plan.items
    written = 0
    conditional_skipped = 0

    if config.apply:
        if config.upload_raw:
            session.client("s3").upload_file(
                str(config.stats_path),
                config.raw_bucket,
                config.raw_key,
            )
        client = session.client("dynamodb")
        for item in planned_items:
            try:
                _put_missing_item(client, config.table_name, item)
                written += 1
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code")
                if code == "ConditionalCheckFailedException":
                    conditional_skipped += 1
                    continue
                raise

    output = {
        "mode": "apply" if config.apply else "dry-run",
        "config": {
            **asdict(config),
            "stats_path": str(config.stats_path),
            "city_lookup_path": str(config.city_lookup_path),
        },
        "summary": asdict(plan.summary),
        "selected_item_count": len(planned_items),
        "written": written,
        "conditional_skipped": conditional_skipped,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _query_entity(
    table: Any, index_name: str, entity_type: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs = {
        "IndexName": index_name,
        "KeyConditionExpression": Key("entity_type").eq(entity_type),
    }
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def _read_json_mapping(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"expected JSON object: {path}"
        raise RuntimeError(msg)
    return {
        str(key): value for key, value in payload.items() if isinstance(value, dict)
    }


def _read_string_mapping(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"expected JSON object: {path}"
        raise RuntimeError(msg)
    return {str(key): str(value) for key, value in payload.items()}


def _put_missing_item(client: Any, table_name: str, item: dict[str, Any]) -> None:
    serializer = TypeSerializer()
    client.put_item(
        TableName=table_name,
        Item={
            key: serializer.serialize(_coerce_value(value))
            for key, value in item.items()
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def _coerce_value(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_coerce_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_value(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    raise SystemExit(main())
