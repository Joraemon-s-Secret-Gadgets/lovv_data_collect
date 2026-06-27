"""
Merge pipeline for combining Wikipedia metadata with visitor statistics.

This module reads cities.json (Wikipedia metadata) and
monthly_visitor_averages.json (DataLab visitor statistics), then produces
per-city final output files in data/KR/final/{CITY_EN}.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Tracks outcomes of the merge operation."""

    merged_count: int = 0
    wikipedia_only_count: int = 0
    visitor_only_count: int = 0
    total: int = 0


def merge_city_with_visitor_stats(
    cities_path: Path,
    visitor_stats_path: Path,
    output_dir: Path,
) -> MergeResult:
    """Embed visitor_statistics into each city's final output file.

    - Cities with both sources: full merge (metadata + visitor_statistics)
    - Cities with only Wikipedia metadata: mark visitor_statistics as incomplete
    - Cities with only visitor stats: mark metadata as incomplete

    Outputs per-city JSON files to *output_dir*/{CITY_EN}.json.

    Args:
        cities_path: Path to cities.json (Wikipedia metadata).
        visitor_stats_path: Path to monthly_visitor_averages.json.
        output_dir: Directory to write final per-city JSON files.

    Returns:
        MergeResult summarizing the merge outcomes.
    """
    result = MergeResult()

    # Load Wikipedia metadata
    wiki_cities: dict[str, dict[str, Any]] = {}
    if cities_path.exists():
        try:
            raw_cities = json.loads(cities_path.read_text(encoding="utf-8"))
            for city in raw_cities:
                city_en = city.get("city_name_en", "")
                if city_en:
                    wiki_cities[city_en] = city
        except Exception as e:
            logger.error("Failed to load cities.json: %s", e)

    # Load visitor statistics
    visitor_stats: dict[str, dict[str, Any]] = {}
    if visitor_stats_path.exists():
        try:
            visitor_stats = json.loads(visitor_stats_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to load visitor stats: %s", e)

    # Determine all unique city names across both sources
    all_city_names = set(wiki_cities.keys()) | set(visitor_stats.keys())

    output_dir.mkdir(parents=True, exist_ok=True)

    for city_en in sorted(all_city_names):
        has_wiki = city_en in wiki_cities
        has_visitor = city_en in visitor_stats

        # Build the final output structure
        final_output: dict[str, Any] = {}

        if has_wiki:
            final_output["meta"] = wiki_cities[city_en]
        else:
            final_output["meta"] = {
                "city_name_en": city_en,
                "_status": "incomplete",
                "_note": "Wikipedia metadata not yet collected for this municipality.",
            }

        if has_visitor:
            final_output["visitor_statistics"] = visitor_stats[city_en]
        else:
            final_output["visitor_statistics"] = {
                "_status": "incomplete",
                "_note": "Visitor statistics not yet collected for this municipality.",
            }

        # Track merge outcome
        if has_wiki and has_visitor:
            result.merged_count += 1
        elif has_wiki:
            result.wikipedia_only_count += 1
        else:
            result.visitor_only_count += 1

        # Write per-city output file
        output_file = output_dir / f"{city_en}.json"
        output_file.write_text(
            json.dumps(final_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    result.total = len(all_city_names)
    logger.info(
        "Merge complete: %d merged, %d wiki-only, %d visitor-only (total: %d)",
        result.merged_count,
        result.wikipedia_only_count,
        result.visitor_only_count,
        result.total,
    )
    return result
