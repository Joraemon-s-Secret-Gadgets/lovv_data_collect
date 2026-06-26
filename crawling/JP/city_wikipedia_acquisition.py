"""
Wikipedia 우선 도시 데이터 취득 CLI 진입점.

재사용 가능한 구현은 `crawling.JP` 아래의 집중 모듈에 있다.
이 모듈은 기존 명령과 가져오기 경로를 안정적으로 유지한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crawling.JP.normalizer import build_city_record
from crawling.JP.pipeline import acquire_city_data, load_targets
from crawling.JP.prefectures import detect_prefecture
from crawling.JP.wikipedia_client import MediaWikiClient, WikipediaHtmlClient


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire Japan city data from Wikipedia first.")
    parser.add_argument("titles", nargs="*", help="Wikipedia city page titles.")
    parser.add_argument("--input", type=Path, help="JSON array file containing city page titles.")
    parser.add_argument("--lang", default="ko", help="Source Wikipedia language for positional or string targets.")
    parser.add_argument("--default-prefecture-id", default="", help="Fallback prefecture id for trusted target lists.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/JP"))
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


# 파일 이력
# 2026-06-04: 재사용 코드를 분리한 뒤 모듈을 CLI 래퍼로 전환했다.
