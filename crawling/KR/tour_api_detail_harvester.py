"""Extract city-detail payloads from Gloveman/tour-api-korea artifacts.

The module reads a KR city list (city_name_en, city_id, city_name_ko) and resolves
matching files in the upstream repository:
- data/raw/final/{city_name}.json
- data/city/{city_name}.json
Optionally a city-specific seed JSON can be provided when repo files are missing.

Output is written per city as JSON under the configured output directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from typing import Any, Iterable


UPSTREAM_DEFAULT_URL = "https://github.com/Gloveman/tour-api-korea"


@dataclass(frozen=True)
class CityTarget:
    city_id: str
    city_name_ko: str
    city_name_en: str
    prefecture_id: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract detailed city data from tour-api-korea compatible outputs.",
    )
    parser.add_argument(
        "--cities-json",
        type=Path,
        default=Path("data/KR/cities.json"),
        help="Path to KR city list JSON generated in earlier steps.",
    )
    parser.add_argument(
        "--repo-url",
        default=UPSTREAM_DEFAULT_URL,
        help="Upstream repository URL (used when local repo is not provided).",
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        help=(
            "Local path to tour-api-korea checkout. "
            "If omitted, a temporary clone is used."
        ),
    )
    parser.add_argument(
        "--repo-branch",
        default="main",
        help="Branch to use when cloning upstream repository.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/KR/details"),
        help="Directory where city detail JSON files are saved.",
    )
    parser.add_argument(
        "--seed-json",
        type=Path,
        help=(
            "Optional seed JSON (붙인 데이터) used when repo output for a city is missing. "
            "JSON keys must match city detail structure."
        ),
    )
    parser.add_argument(
        "--city-id",
        action="append",
        help="Optional filter by city_id. Repeatable.",
    )
    parser.add_argument(
        "--city-name-en",
        action="append",
        help="Optional filter by city_name_en. Repeatable.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwrite existing output files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve source files and print matching paths without writing output.",
    )
    return parser.parse_args(argv)


def slugify_city_name(value: str) -> str:
    """Normalize city file name for deterministic per-city output."""
    normalized = value.lower().strip().replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_\-]", "", normalized)
    if not normalized:
        normalized = "city"
    return normalized


def resolve_repo_path(repo_path: Path | None, repo_url: str, repo_branch: str) -> Path:
    """Resolve repository path and clone upstream temporarily when needed."""
    if repo_path is not None:
        if not repo_path.exists():
            raise FileNotFoundError(f"repo_path does not exist: {repo_path}")
        return repo_path

    temp_dir = Path(tempfile.gettempdir()) / "tour_api_korea_sync"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / "repo"
    marker = target / ".git"

    if not marker.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1", "-b", repo_branch, repo_url, str(target)],
            check=True,
        )
    return target


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_city_targets(
    cities_json_path: Path,
    city_ids: list[str] | None = None,
    city_names_en: list[str] | None = None,
) -> list[CityTarget]:
    raw_data = _read_json(cities_json_path)
    if not isinstance(raw_data, list):
        raise ValueError(f"Expected list in city json: {cities_json_path}")

    filtered: list[CityTarget] = []
    city_id_set = set([item.upper() for item in city_ids or []])
    city_name_en_set = set([item.lower() for item in city_names_en or []])

    for item in raw_data:
        if not isinstance(item, dict):
            continue

        city_id = str(item.get("city_id", "")).strip()
        if not city_id:
            continue
        city_name_ko = str(item.get("city_name_ko", "")).strip()
        city_name_en = str(item.get("city_name_en", "")).strip()

        if city_id_set and city_id.upper() not in city_id_set:
            continue
        if city_name_en_set and (city_name_en or "").lower() not in city_name_en_set:
            continue

        filtered.append(
            CityTarget(
                city_id=city_id,
                city_name_ko=city_name_ko,
                city_name_en=city_name_en,
                prefecture_id=(item.get("prefecture_id") or None),
            )
        )

    if not filtered:
        return []
    return filtered


def _candidate_basenames(city: CityTarget) -> list[str]:
    names = [city.city_name_en, city.city_name_en.replace(" ", "_"), city.city_id]
    expanded: list[str] = []
    for name in names:
        if not isinstance(name, str):
            continue
        value = name.strip()
        if not value:
            continue
        expanded.append(value)
        expanded.append(value.lower())
        expanded.append(value.replace(" ", "_"))
        expanded.append(value.replace("-", "_"))
    return list(dict.fromkeys(expanded))


def _contains_city_signature(payload: Any, city: CityTarget) -> bool:
    if not isinstance(payload, dict):
        return False
    meta = payload.get("meta") or {}
    if isinstance(meta, dict):
        city_name_en = str(meta.get("city_name_en", "")).strip().upper()
        city_name_ko = str(meta.get("city_name_ko", "")).strip()
        city_id = str(meta.get("city_id", "")).strip()
        if city_name_en == city.city_name_en.upper() or city_name_ko == city.city_name_ko:
            return True
        if city_id and city_id == city.city_id:
            return True
    if str(payload.get("city_name_en", "")).strip().upper() == city.city_name_en.upper():
        return True
    if str(payload.get("city_id", "")).strip() == city.city_id:
        return True
    if str(payload.get("name_ko", "")).strip() == city.city_name_ko:
        return True
    return False


def _is_city_detail_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return "attractions" in payload or "festivals" in payload or "visitor_stats" in payload


def find_city_source_paths(repo_root: Path, city: CityTarget) -> list[Path]:
    candidates: list[Path] = []
    basenames = _candidate_basenames(city)
    lookup_roots = [
        repo_root / "data/raw/final",
        repo_root / "data/city",
        repo_root / "data",
    ]

    for root in lookup_roots:
        if not root.exists():
            continue
        for basename in basenames:
            candidate_file = root / f"{basename}.json"
            if candidate_file.exists():
                candidates.append(candidate_file)

    if not candidates:
        # Fallback: scan all jsons and inspect payload signatures.
        for path in repo_root.rglob("*.json"):
            try:
                payload = _read_json(path)
            except Exception:
                continue
            if _contains_city_signature(payload, city) and _is_city_detail_payload(payload):
                candidates.append(path)

    return candidates


def _hash_payload(payload: Any) -> str:
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


def normalize_city_detail(city: CityTarget, payload: Any, source_path: Path | None, seed_path: Path | None) -> dict[str, Any]:
    source_city_name_en = str(
        (
            payload.get("meta", {}).get("city_name_en")
            if isinstance(payload, dict) and isinstance(payload.get("meta"), dict)
            else None
        )
        or city.city_name_en
    )
    source_city_name_ko = str(
        (
            payload.get("meta", {}).get("city_name_ko")
            if isinstance(payload, dict) and isinstance(payload.get("meta"), dict)
            else None
        )
        or city.city_name_ko
    )

    attractions = []
    festivals = []
    city_payload = payload if isinstance(payload, dict) else {}

    for item in city_payload.get("attractions", []) or []:
        if not isinstance(item, dict):
            continue
        attractions.append(item)

    for item in city_payload.get("festivals", []) or []:
        if not isinstance(item, dict):
            continue
        festivals.append(item)

    return {
        "city_id": city.city_id,
        "prefecture_id": city.prefecture_id,
        "city_name_en": source_city_name_en,
        "city_name_ko": source_city_name_ko,
        "source_path": str(source_path) if source_path else None,
        "seed_source": str(seed_path) if seed_path else None,
        "attractions_count_filtered": city_payload.get("attractions_count_filtered", len(attractions)),
        "festivals_count_filtered": city_payload.get("festivals_count_filtered", len(festivals)),
        "meta": city_payload.get("meta", {}),
        "attractions": attractions,
        "festivals": festivals,
        "quality": {
            "signature": _hash_payload(city_payload),
            "extracted_by": "tour_api_detail_harvester",
        },
    }


def extract_city_details(
    city_targets: list[CityTarget],
    repo_path: Path,
    output_dir: Path,
    overwrite: bool = False,
    dry_run: bool = False,
    seed_json: Path | None = None,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_payload: Any = _read_json(seed_json) if seed_json else None

    if seed_payload is not None and not isinstance(seed_payload, dict):
        raise ValueError("seed-json must be a JSON object.")

    results: list[dict[str, Any]] = []
    for city in city_targets:
        matches = find_city_source_paths(repo_path, city)
        source_payload: Any = None
        source_path: Path | None = None

        for match in matches:
            try:
                candidate = _read_json(match)
            except Exception:
                continue
            if isinstance(candidate, dict) and _is_city_detail_payload(candidate):
                source_payload = candidate
                source_path = match
                break

        payload = source_payload if isinstance(source_payload, dict) else (seed_payload if seed_payload else {})
        if not payload:
            payload = {}

        result = normalize_city_detail(city, payload, source_path, seed_json)
        result["source_path"] = str(source_path) if source_path else result["source_path"]
        results.append(result)

        if dry_run:
            print(
                "[match]" if source_path else "[no-match]",
                city.city_name_en or city.city_id,
                "->",
                source_path or "(seed/empty)",
            )
            continue

        output_path = output_dir / f"{slugify_city_name(city.city_name_en or city.city_id)}.json"
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Output already exists: {output_path} (use --overwrite)")

        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return results


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        city_targets = load_city_targets(
            args.cities_json,
            city_ids=args.city_id,
            city_names_en=args.city_name_en,
        )
    except Exception as exc:
        print(f"[ERROR] Failed to load city list: {exc}")
        return 1

    if not city_targets:
        print("[WARN] No cities selected.")
        return 0

    try:
        repo_path = resolve_repo_path(args.repo_path, args.repo_url, args.repo_branch)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    try:
        extracted = extract_city_details(
            city_targets=city_targets,
            repo_path=repo_path,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            seed_json=args.seed_json,
        )
    except Exception as exc:
        print(f"[ERROR] Extraction failed: {exc}")
        return 1

    if args.dry_run:
        print(f"[INFO] resolved={len(extracted)} (dry-run)")
    else:
        print(f"[INFO] written={len(extracted)} -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
