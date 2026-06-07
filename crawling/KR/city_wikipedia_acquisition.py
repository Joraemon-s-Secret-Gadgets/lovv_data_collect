"""
CLI entry point for Wikipedia-first South Korea city data acquisition.

The reusable implementation lives in focused modules under `crawling.KR`.
This module keeps the existing command and import surface stable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crawling.KR.pipeline import acquire_city_data, load_targets
from crawling.KR.wikipedia_client import MediaWikiClient, WikipediaHtmlClient


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    titles = load_targets(
        args.input,
        args.titles,
        default_lang=args.lang,
        default_prefecture_id=args.default_prefecture_id,
    )
    if not titles:
        print("Provide city titles as arguments or with --input.", file=sys.stderr)
        return 2
    client = WikipediaHtmlClient() if args.fetcher == "html" else MediaWikiClient()
    acquire_city_data(titles=titles, output_dir=args.output_dir, client=client, source_lang=args.lang)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
