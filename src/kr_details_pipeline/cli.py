"""Command line entrypoint for KR details pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from kr_details_pipeline.raw_ingest import RawIngestConfig, ingest_raw_details


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KR details pipeline utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    raw_ingest = subparsers.add_parser("raw-ingest", help="Upload KR details JSON files to S3 Raw.")
    raw_ingest.add_argument("--input-dir", type=Path, default=Path("data/KR/details"))
    raw_ingest.add_argument("--output-dir", type=Path, default=Path("data/KR/ingest"))
    raw_ingest.add_argument("--bucket", required=True)
    raw_ingest.add_argument("--profile", help="AWS profile name, e.g. skn26_final.")
    raw_ingest.add_argument("--region", default="us-east-1")
    raw_ingest.add_argument("--ingest-date", default=datetime.now().strftime("%Y%m%d"))
    raw_ingest.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "raw-ingest":
        return _raw_ingest(args)
    raise ValueError(f"Unsupported command: {args.command}")


def _raw_ingest(args: argparse.Namespace) -> int:
    import boto3

    session_kwargs = {}
    if args.profile:
        session_kwargs["profile_name"] = args.profile
    if args.region:
        session_kwargs["region_name"] = args.region
    session = boto3.Session(**session_kwargs)
    s3_client = session.client("s3")

    results = ingest_raw_details(
        RawIngestConfig(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            bucket=args.bucket,
            ingest_date=args.ingest_date,
            overwrite=args.overwrite,
        ),
        s3_client,
    )
    uploaded = sum(1 for result in results if result.status == "uploaded")
    skipped = sum(1 for result in results if result.status == "skipped")
    failed = sum(1 for result in results if result.status == "failed")
    print(f"[INFO] raw-ingest completed uploaded={uploaded} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
