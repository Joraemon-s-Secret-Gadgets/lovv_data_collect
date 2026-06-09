"""Collect Gangwon and Gyeongbuk TourAPI city-detail JSON files.

This module performs the full city-detail acquisition flow:
1. Load legal-dong region/sigungu targets.
2. Fetch attractions and festivals from KorService2 list endpoints.
3. Filter records by theme mapping.
4. Attach detailCommon2/detailIntro2 data.
5. Write one sample-shaped JSON file per city under data/KR/details.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from crawling.KR.tour_api_city_detail_acquisition import (
    TourAPIClient,
    TourAPIConfig,
    collect_city_detail,
    load_service_keys,
)
from crawling.KR.tour_api_detail_harvester import slugify_city_name


DEFAULT_REFERENCE_DIR = Path(".cache/tour_api_korea_repo/data")
DEFAULT_OUTPUT_DIR = Path("data/KR/details")
TARGET_REGION_CODES = {"51", "47"}  # Gangwon State, Gyeongsangbuk-do
TARGET_THEMES = {"온천·휴양", "바다·해안", "역사·전통", "미식·노포", "자연·트레킹", "예술·감성"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect KR city details for Gangwon and Gyeongbuk.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--reference-dir", type=Path, default=DEFAULT_REFERENCE_DIR)
    parser.add_argument("--cities-json", type=Path, default=Path("data/KR/cities.json"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--work-dir", type=Path, default=Path("data/KR/raw_tour_api"))
    parser.add_argument("--detail-cache-dir", type=Path, default=Path("data/KR/detail_cache"))
    parser.add_argument("--city-name-ko", action="append", help="Optional city-name filter. Repeatable.")
    parser.add_argument("--limit-cities", type=int, help="Optional city count limit for smoke runs.")
    parser.add_argument("--limit-items-per-city", type=int, help="Optional item count limit per city.")
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def collect_regions(args: argparse.Namespace) -> list[Path]:
    service_keys = load_service_keys(args.env_file)
    client = TourAPIClient(
        TourAPIConfig(
            service_keys=service_keys,
            request_delay_seconds=args.request_delay_seconds,
            max_retries=args.max_retries,
        ),
    )

    reference_dir = args.reference_dir
    targets = _load_targets(reference_dir / "ldong_sigungu.json", args.city_name_ko)
    if args.limit_cities is not None:
        targets = targets[: max(args.limit_cities, 0)]

    city_name_lookup = _load_city_name_lookup(args.cities_json)
    attraction_theme_map = _build_theme_map(reference_dir / "theme_mapping.json", excluded_theme_names={"제외(기타/숙박/코스/축제)"})
    festival_theme_map = _build_theme_map(reference_dir / "festival_mapping.json", excluded_theme_names={"제외"})

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.detail_cache_dir.mkdir(parents=True, exist_ok=True)

    written_outputs: list[Path] = []
    for index, target in enumerate(targets, start=1):
        city_name_ko = str(target["lDongSignguNm"])
        city_name_en = city_name_lookup.get(city_name_ko, _fallback_city_name_en(city_name_ko))
        output_path = args.output_dir / f"{slugify_city_name(city_name_en)}.json"
        if output_path.exists() and not args.overwrite:
            print(f"[{index}/{len(targets)}] skip existing {city_name_ko} ({city_name_en})", flush=True)
            written_outputs.append(output_path)
            continue

        print(f"[{index}/{len(targets)}] collecting {target['lDongRegnNm']} {city_name_ko} ({city_name_en})", flush=True)

        list_payload = collect_city_list(
            client=client,
            target=target,
            city_name_en=city_name_en,
            attraction_theme_map=attraction_theme_map,
            festival_theme_map=festival_theme_map,
        )

        list_path = args.work_dir / f"{slugify_city_name(city_name_en)}_filtered.json"
        list_path.write_text(json.dumps(list_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        collect_city_detail(
            city_list_path=list_path,
            output_dir=args.output_dir,
            detail_cache_dir=args.detail_cache_dir,
            client=client,
            overwrite=args.overwrite,
            limit=args.limit_items_per_city,
        )
        written_outputs.append(output_path)
        time.sleep(0.3)

    return written_outputs


def collect_city_list(
    client: TourAPIClient,
    target: dict[str, Any],
    city_name_en: str,
    attraction_theme_map: dict[str, str],
    festival_theme_map: dict[str, str],
) -> dict[str, Any]:
    base_params = {
        "lDongRegnCd": target["lDongRegnCd"],
        "lDongSignguCd": target["lDongSignguCd"],
    }
    raw_attractions = fetch_all_items(client, "areaBasedList2", base_params)
    raw_festivals = fetch_all_items(
        client,
        "searchFestival2",
        {
            **base_params,
            "eventStartDate": "20250101",
        },
    )

    attractions = _filter_records(raw_attractions, attraction_theme_map, excluded_theme_names={"제외(기타/숙박/코스/축제)"})
    festivals = _filter_records(raw_festivals, festival_theme_map, excluded_theme_names={"제외"})
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "meta": {
            "province": target["lDongRegnNm"],
            "city_name_ko": target["lDongSignguNm"],
            "city_name_en": city_name_en,
            "lDongRegnCd": target["lDongRegnCd"],
            "lDongSignguCd": target["lDongSignguCd"],
            "scraped_at": scraped_at,
        },
        "attractions_count_raw": len(raw_attractions),
        "festivals_count_raw": len(raw_festivals),
        "attractions_count_filtered": len(attractions),
        "festivals_count_filtered": len(festivals),
        "attractions": attractions,
        "festivals": festivals,
    }


def fetch_all_items(client: TourAPIClient, endpoint: str, params: dict[str, Any], page_size: int = 500) -> list[dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    page_no = 1
    while True:
        payload = client.request(
            endpoint,
            {
                **params,
                "numOfRows": page_size,
                "pageNo": page_no,
            },
        )
        body = payload.get("response", {}).get("body", {})
        items_container = body.get("items")
        item = items_container.get("item") if isinstance(items_container, dict) else []
        items = item if isinstance(item, list) else ([item] if isinstance(item, dict) else [])
        all_items.extend([entry for entry in items if isinstance(entry, dict)])

        total_count = int(body.get("totalCount") or len(all_items))
        if len(all_items) >= total_count or len(items) < page_size:
            break
        page_no += 1
        time.sleep(0.2)
    return all_items


def _load_targets(path: Path, city_names_ko: list[str] | None) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected target list: {path}")
    city_filter = set(city_names_ko or [])
    targets = [
        item for item in payload
        if isinstance(item, dict)
        and str(item.get("lDongRegnCd")) in TARGET_REGION_CODES
        and (not city_filter or str(item.get("lDongSignguNm")) in city_filter)
    ]
    if not targets:
        raise ValueError("No Gangwon/Gyeongbuk targets selected.")
    return targets


def _load_city_name_lookup(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}
    lookup: dict[str, str] = {}
    for item in payload:
        if isinstance(item, dict):
            city_name_ko = str(item.get("city_name_ko") or "")
            city_name_en = str(item.get("city_name_en") or "")
            if city_name_ko and city_name_en:
                lookup[city_name_ko] = city_name_en
    return lookup


def _build_theme_map(path: Path, excluded_theme_names: set[str]) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected theme mapping object: {path}")

    theme_map: dict[str, str] = {}
    for theme_name, records in payload.items():
        if theme_name not in TARGET_THEMES:
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict) or _should_exclude(record):
                continue
            code = str(record.get("code") or "")
            if code and theme_name not in excluded_theme_names:
                theme_map[code] = theme_name
    return theme_map


def _filter_records(records: list[dict[str, Any]], theme_map: dict[str, str], excluded_theme_names: set[str]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for record in records:
        if record.get("lclsSystm1") == "C01":
            continue
        code = str(record.get("lclsSystm3") or record.get("cat3") or "")
        theme = theme_map.get(code)
        if not theme or theme in excluded_theme_names:
            continue
        item = dict(record)
        item["_assigned_theme"] = theme
        filtered.append(item)
    return filtered


def _should_exclude(record: dict[str, Any]) -> bool:
    exclude_large = {"체험관광"}
    exclude_middle = {"기타문화관광지", "레저스포츠시설", "교육시설", "공연시설", "복합관광시설"}
    exclude_names = {"기타주점", "클럽", "기타간이음식", "북한관광지", "기타안보관광지", "기타 종교성지", "약수터"}
    return (
        str(record.get("large_category") or "") in exclude_large
        or str(record.get("middle_category") or "") in exclude_middle
        or str(record.get("name") or "") in exclude_names
    )


def _fallback_city_name_en(city_name_ko: str) -> str:
    return city_name_ko.replace(" ", "_")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        written = collect_regions(args)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"[INFO] written {len(written)} city detail files -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
