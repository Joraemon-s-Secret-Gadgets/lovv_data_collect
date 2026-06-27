"""
CLI entry point for Wikipedia-first South Korea city data acquisition.

The reusable implementation lives in focused modules under `crawling.KR`.
This module keeps the existing command and import surface stable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from crawling.KR.pipeline import acquire_city_data, acquire_province, acquire_all_provinces, load_targets
from crawling.KR.wikipedia_client import MediaWikiClient, WikipediaHtmlClient

# Maps province ISO codes (KR-XX) to their corresponding target file names.
PROVINCE_TARGET_MAP: Final[dict[str, str]] = {
    "KR-11": "seoul_municipalities_ko.json",
    "KR-26": "busan_municipalities_ko.json",
    "KR-27": "daegu_municipalities_ko.json",
    "KR-28": "incheon_municipalities_ko.json",
    "KR-29": "gwangju_municipalities_ko.json",
    "KR-30": "daejeon_municipalities_ko.json",
    "KR-31": "ulsan_municipalities_ko.json",
    "KR-36": "sejong_municipalities_ko.json",
    "KR-41": "gyeonggi_municipalities_ko.json",
    "KR-42": "gangwon_municipalities_ko.json",
    "KR-43": "chungbuk_municipalities_ko.json",
    "KR-44": "chungnam_municipalities_ko.json",
    "KR-45": "jeonbuk_municipalities_ko.json",
    "KR-46": "jeonnam_municipalities_ko.json",
    "KR-47": "gyeongbuk_municipalities_ko.json",
    "KR-48": "gyeongnam_municipalities_ko.json",
    "KR-50": "jeju_municipalities_ko.json",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire South Korea city data from Wikipedia first.")
    parser.add_argument("titles", nargs="*", help="Wikipedia city page titles.")
    parser.add_argument("--input", type=Path, help="JSON array file containing city page titles.")
    parser.add_argument("--lang", default="ko", help="Source Wikipedia language for positional or string targets.")
    parser.add_argument("--default-prefecture-id", default="", help="Fallback prefecture (province) id for trusted target lists.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/KR"))
    parser.add_argument(
        "--fetcher",
        choices=("html", "api"),
        default="html",
        help="Wikipedia fetcher implementation. HTML is the default to avoid MediaWiki API timeout issues.",
    )
    # Province-level batch execution arguments
    parser.add_argument(
        "--province-id",
        type=str,
        default=None,
        help="Process a single province by ISO code (e.g., KR-11). "
        "Mutually exclusive with --input and positional titles.",
    )
    parser.add_argument(
        "--all-provinces",
        action="store_true",
        default=False,
        help="Process all 17 provinces sequentially. "
        "Mutually exclusive with --input, --province-id, and positional titles.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        default=False,
        help="Force re-collection of data even if it already exists.",
    )
    parser.add_argument(
        "--upload-to-s3",
        action="store_true",
        default=False,
        help="Upload results to S3 after collection.",
    )
    parser.add_argument(
        "--collect-visitor-stats",
        action="store_true",
        default=False,
        help="Run DataLab visitor statistics collection after Wikipedia acquisition.",
    )
    parser.add_argument(
        "--visitor-year",
        type=int,
        default=2025,
        help="Target year for visitor statistics collection (default: 2025).",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        default=False,
        help="Run merge pipeline to combine Wikipedia metadata + visitor statistics.",
    )
    parser.add_argument(
        "--visitor-output",
        type=Path,
        default=Path("data/visitor/monthly_visitor_averages.json"),
        help="Path for visitor statistics output file.",
    )
    parser.add_argument(
        "--final-output-dir",
        type=Path,
        default=Path("data/KR/final"),
        help="Directory for merged per-city output files.",
    )
    args = parser.parse_args(argv)

    # Validate mutual exclusivity
    source_flags = []
    if args.input:
        source_flags.append("--input")
    if args.titles:
        source_flags.append("positional titles")
    if args.province_id:
        source_flags.append("--province-id")
    if args.all_provinces:
        source_flags.append("--all-provinces")

    if len(source_flags) > 1:
        parser.error(
            f"The following options are mutually exclusive: {', '.join(source_flags)}. "
            "Use only one input source."
        )

    # Validate province-id value
    if args.province_id and args.province_id not in PROVINCE_TARGET_MAP:
        parser.error(
            f"Invalid province ID '{args.province_id}'. "
            f"Valid values: {', '.join(sorted(PROVINCE_TARGET_MAP.keys()))}"
        )

    return args


def _get_targets_dir() -> Path:
    """Return the path to the targets directory."""
    return Path(__file__).parent / "targets"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    client = WikipediaHtmlClient() if args.fetcher == "html" else MediaWikiClient()

    # Province-level batch modes
    if args.all_provinces:
        results = acquire_all_provinces(
            output_dir=args.output_dir,
            client=client,
            targets_dir=_get_targets_dir(),
        )
        total_new = sum(r.newly_acquired for r in results)
        total_skipped = sum(r.skipped for r in results)
        total_failed = sum(r.failed for r in results)
        print(
            f"All provinces complete: {total_new} new, "
            f"{total_skipped} skipped, {total_failed} failed."
        )
        if args.collect_visitor_stats:
            _run_visitor_collection(args)
        if args.merge:
            _run_merge(args)
        if args.upload_to_s3:
            _upload_results(args.output_dir)
        return 0

    if args.province_id:
        result = acquire_province(
            province_id=args.province_id,
            output_dir=args.output_dir,
            client=client,
            targets_dir=_get_targets_dir(),
        )
        print(
            f"Province {args.province_id} complete: {result.newly_acquired} new, "
            f"{result.skipped} skipped, {result.failed} failed."
        )
        if result.failed_titles:
            print(f"Failed titles: {result.failed_titles}", file=sys.stderr)
        if args.collect_visitor_stats:
            _run_visitor_collection(args)
        if args.merge:
            _run_merge(args)
        if args.upload_to_s3:
            _upload_results(args.output_dir)
        return 0

    # Legacy single-file / positional mode
    titles = load_targets(
        args.input,
        args.titles,
        default_lang=args.lang,
        default_prefecture_id=args.default_prefecture_id,
    )
    if not titles:
        print("Provide city titles as arguments, --input, --province-id, or --all-provinces.", file=sys.stderr)
        return 2
    acquire_city_data(titles=titles, output_dir=args.output_dir, client=client, source_lang=args.lang)

    # Post-acquisition steps
    if args.collect_visitor_stats:
        _run_visitor_collection(args)
    if args.merge:
        _run_merge(args)
    if args.upload_to_s3:
        _upload_results(args.output_dir)
    return 0


def _upload_results(output_dir: Path) -> None:
    """Upload cities.json and prefectures.json to S3."""
    try:
        from crawling.KR.s3_uploader import upload_crawl_results, S3UploadConfig
        import os

        bucket = os.environ.get("S3_BUCKET", "")
        if not bucket:
            print("Warning: S3_BUCKET not set, skipping S3 upload.", file=sys.stderr)
            return

        config = S3UploadConfig(bucket=bucket)
        results = upload_crawl_results(output_dir, config)
        for r in results:
            print(f"  S3 {r.status}: {r.s3_key}" + (f" ({r.error})" if r.error else ""))
    except ImportError:
        print("Warning: s3_uploader not available, skipping S3 upload.", file=sys.stderr)
    except Exception as e:
        print(f"Error uploading to S3: {e}", file=sys.stderr)


def _run_visitor_collection(args: "argparse.Namespace") -> None:
    """Run DataLab visitor statistics collection."""
    try:
        from crawling.KR.datalab_collector import (
            BigDataClient,
            SignguCodeMapping,
            collect_visitor_statistics,
        )

        print(f"Collecting visitor statistics for year {args.visitor_year}...")
        mapping = SignguCodeMapping()
        client = BigDataClient()
        collect_visitor_statistics(
            year=args.visitor_year,
            mapping=mapping,
            client=client,
            output_path=args.visitor_output,
            force_refresh=args.force_refresh,
        )
        print(f"Visitor statistics saved to {args.visitor_output}")
    except Exception as e:
        print(f"Error collecting visitor statistics: {e}", file=sys.stderr)


def _run_merge(args: "argparse.Namespace") -> None:
    """Run merge pipeline to combine Wikipedia metadata + visitor statistics."""
    try:
        from crawling.KR.merge_pipeline import merge_city_with_visitor_stats

        cities_path = args.output_dir / "cities.json"
        print(f"Merging Wikipedia + visitor data → {args.final_output_dir}...")
        result = merge_city_with_visitor_stats(
            cities_path=cities_path,
            visitor_stats_path=args.visitor_output,
            output_dir=args.final_output_dir,
        )
        print(
            f"Merge complete: {result.merged_count} merged, "
            f"{result.wikipedia_only_count} wiki-only, "
            f"{result.visitor_only_count} visitor-only "
            f"(total: {result.total})"
        )
    except Exception as e:
        print(f"Error running merge pipeline: {e}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
