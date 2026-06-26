"""Command line entrypoint for KR unified preprocessing pipeline.

Provides three subcommands:
  - preprocess: Run preprocessing stages (Wikipedia, TourAPI Region, TourAPI Detail)
  - e2e: Run End-to-End pipeline (S3 read → DynamoDB load → Vector rebuild)
  - local-test: Run province-scoped E2E validation locally

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 14.1, 14.7, 14.8
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments with subcommands."""
    parser = argparse.ArgumentParser(
        description="KR unified preprocessing pipeline utilities."
    )
    parser.add_argument("--profile", default=None, help="AWS profile name.")
    parser.add_argument("--region", default="us-east-1", help="AWS region.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- preprocess subcommand ---
    preprocess = subparsers.add_parser(
        "preprocess",
        help="Run preprocessing stages (Wikipedia, TourAPI Region, TourAPI Detail).",
    )
    preprocess.add_argument(
        "--stage",
        action="append",
        dest="stages",
        choices=["wikipedia", "tourapi-region", "tourapi-detail"],
        help="Stage(s) to execute. Repeat for multiple. Default: all.",
    )
    preprocess.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/KR/"),
        help="Directory for JSON output files.",
    )
    preprocess.add_argument(
        "--province-id",
        default=None,
        help="Limit processing to a specific province (e.g. KR-42).",
    )
    preprocess.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-collect data for already-collected records.",
    )
    preprocess.add_argument(
        "--skip-images",
        action="store_true",
        help="Disable image URL resolution.",
    )
    preprocess.add_argument(
        "--force-image-update",
        action="store_true",
        help="Replace existing image_url with new one during merge.",
    )

    # --- e2e subcommand ---
    e2e = subparsers.add_parser(
        "e2e",
        help="Run End-to-End pipeline (S3 → DynamoDB → Vector rebuild).",
    )
    e2e.add_argument(
        "--stage",
        dest="stages",
        action="append",
        choices=["load", "vector-build"],
        help="E2E stage(s) to execute. Default: full sequence (load → vector-build).",
    )
    e2e.add_argument(
        "--bucket",
        default="",
        help="S3 pipeline bucket name.",
    )
    e2e.add_argument(
        "--ingest-date",
        default="",
        help="Target ingest date partition (e.g. 20250115). Default: latest.",
    )
    e2e.add_argument(
        "--table-name",
        default="TourKoreaDomainDataV2",
        help="DynamoDB table name.",
    )
    e2e.add_argument(
        "--rebuild-mode",
        default="full",
        choices=["full", "incremental"],
        help="Vector rebuild mode.",
    )

    # --- local-test subcommand ---
    local_test = subparsers.add_parser(
        "local-test",
        help="Run province-scoped E2E validation locally.",
    )
    local_test.add_argument(
        "--province-id",
        required=True,
        help="Province key to scope all operations (e.g. KR-42). Required.",
    )
    local_test.add_argument(
        "--bucket",
        default="",
        help="S3 pipeline bucket name.",
    )
    local_test.add_argument(
        "--ingest-date",
        default="",
        help="Target ingest date partition. Default: latest.",
    )
    local_test.add_argument(
        "--table-name",
        default="TourKoreaDomainDataV2",
        help="DynamoDB table name.",
    )
    local_test.add_argument(
        "--vector-bucket",
        default="lovv-vector-dev",
        help="S3 Vectors bucket name.",
    )
    local_test.add_argument(
        "--index-name",
        default="kr-tour-domain-v1",
        help="Vector index name.",
    )

    return parser.parse_args(argv)


def _create_session(args: argparse.Namespace) -> Any:
    """Create a boto3 session from CLI arguments."""
    import boto3

    session_kwargs: dict[str, str] = {}
    if args.profile:
        session_kwargs["profile_name"] = args.profile
    if args.region:
        session_kwargs["region_name"] = args.region
    return boto3.Session(**session_kwargs)


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    args = parse_args(argv)
    _setup_logging(args.verbose)

    if args.command == "preprocess":
        return _preprocess(args)
    if args.command == "e2e":
        return _e2e(args)
    if args.command == "local-test":
        return _local_test(args)

    print(f"[ERROR] Unsupported command: {args.command}", file=sys.stderr)
    return 2


def _preprocess(args: argparse.Namespace) -> int:
    """Execute preprocessing stages via the UnifiedPipeline orchestrator.

    Wires CLI → orchestrator.UnifiedPipeline (Requirement 10.6, 13.2).
    """
    from kr_unified_pipeline.models import PipelineConfig
    from kr_unified_pipeline.orchestrator import UnifiedPipeline

    config = PipelineConfig(
        output_dir=str(args.output_dir),
        stages=args.stages or [],
        province_id=args.province_id,
        force_refresh=args.force_refresh,
        skip_images=args.skip_images,
        force_image_update=args.force_image_update,
        verbose=args.verbose,
        profile=args.profile,
        region=args.region,
    )

    pipeline = UnifiedPipeline(config=config)
    context = pipeline.run()

    # Print summary
    summary = pipeline.get_summary(context)
    print(
        f"[INFO] preprocess completed: "
        f"records={summary['total_records']}, "
        f"images={summary['total_images_collected']}, "
        f"review={summary['records_transitioned_to_review']}, "
        f"errors={summary['total_errors']}"
    )

    return 1 if summary["total_errors"] > 0 else 0


def _e2e(args: argparse.Namespace) -> int:
    """Execute End-to-End pipeline (S3 → DynamoDB → Vector rebuild).

    Delegates to the same logic as pipeline_handler.handler for load/vector-build.
    Wires CLI → s3_reader → dynamodb_loader → vector_rebuilder (Requirement 13.2).
    """
    import boto3

    from kr_unified_pipeline.handlers.pipeline_handler import handler

    session = _create_session(args)

    # Determine command for the handler
    stages = args.stages or []
    if not stages:
        command = "e2e"
    elif len(stages) == 1:
        command = stages[0]
    else:
        command = "e2e"

    # Build event matching handler's expected format
    event: dict[str, Any] = {
        "command": command,
        "bucket": args.bucket,
        "ingest_date": args.ingest_date,
        "table_name": args.table_name,
        "rebuild_mode": args.rebuild_mode,
    }

    # For CLI execution, set environment variables so handler can use boto3 with profile
    import os

    if args.profile:
        os.environ["AWS_PROFILE"] = args.profile
    if args.region:
        os.environ["AWS_DEFAULT_REGION"] = args.region

    result = handler(event, None)
    status_code = result.get("statusCode", 500)
    summary = result.get("summary", {})

    print(
        f"[INFO] e2e completed: "
        f"status={status_code}, "
        f"s3_files={summary.get('s3_files_read', 0)}, "
        f"loaded={summary.get('records_loaded', 0)}, "
        f"vectors={summary.get('vectors_upserted', 0)}, "
        f"elapsed={summary.get('execution_time_seconds', 0):.2f}s"
    )

    if summary.get("errors"):
        for err in summary["errors"]:
            print(f"[ERROR] {err}", file=sys.stderr)

    return 0 if status_code == 200 else 1


def _local_test(args: argparse.Namespace) -> int:
    """Execute province-scoped E2E validation locally.

    Wires CLI → LocalTestRunner (Requirements 14.1, 14.7).
    """
    from kr_unified_pipeline.local_test import LocalTestRunner

    session = _create_session(args)

    runner = LocalTestRunner(
        province_id=args.province_id,
        bucket=args.bucket,
        ingest_date=args.ingest_date,
        table_name=args.table_name,
        vector_bucket=args.vector_bucket,
        index_name=args.index_name,
        session=session,
    )

    summary = runner.run()

    print(
        f"[INFO] local-test completed: "
        f"province={summary.province_id}, "
        f"verdict={summary.verdict}, "
        f"s3_read={summary.items_read_from_s3}, "
        f"loaded={summary.items_loaded_to_dynamodb}, "
        f"vectors={summary.vectors_built}, "
        f"elapsed={summary.execution_time_seconds:.2f}s"
    )

    if summary.failed_items:
        print(f"[WARN] Failed items: {', '.join(summary.failed_items[:10])}", file=sys.stderr)

    return 0 if summary.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
