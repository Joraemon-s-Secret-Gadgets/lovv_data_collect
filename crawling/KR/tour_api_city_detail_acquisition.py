"""Collect TourAPI detail data for one city list payload.

Input is a city-level list JSON with the same shape as tour-api-korea
`data/raw/list_by_city/{city_en}_filtered.json`:

{
  "meta": {"city_name_en": "ANDONG", "city_name_ko": "안동시", ...},
  "attractions": [{"contentid": "...", "contenttypeid": "12", ...}],
  "festivals": [{"contentid": "...", "contenttypeid": "15", ...}]
}

The collector calls KorService2 `detailCommon2` and `detailIntro2`, caches each
content detail by contentid, and writes one city JSON whose item structure
matches the sample payload already used by the pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from crawling.KR.tour_api_detail_harvester import _enrich_item_status


TOUR_API_BASE_URL = "http://apis.data.go.kr/B551011/KorService2"
DEFAULT_MOBILE_OS = "ETC"
DEFAULT_MOBILE_APP = "Lovv"


class HttpSession(Protocol):
    def get(self, url: str, params: dict[str, Any], timeout: int) -> Any:
        ...


class TourAPIError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"TourAPI error {code}: {message}")


@dataclass(frozen=True)
class TourAPIConfig:
    service_keys: tuple[str, ...]
    base_url: str = TOUR_API_BASE_URL
    mobile_os: str = DEFAULT_MOBILE_OS
    mobile_app: str = DEFAULT_MOBILE_APP
    timeout_seconds: int = 30
    request_delay_seconds: float = 0.5
    max_retries: int = 3


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect TourAPI detail data for city list JSON files.")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="City list JSON containing meta, attractions, and festivals.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/KR/details"),
        help="Directory where final city JSON is written.",
    )
    parser.add_argument(
        "--detail-cache-dir",
        type=Path,
        default=Path("data/KR/detail_cache"),
        help="Directory for cached {contentid}.json detail API responses.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional env file containing TOUR_API_KEY or TOUR_API_KEYS.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output city JSON.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional max number of total items to collect for smoke tests.",
    )
    return parser.parse_args(argv)


def load_service_keys(env_file: Path | None = None) -> tuple[str, ...]:
    keys: list[str] = []
    if env_file and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() in {"TOUR_API_KEY", "TOUR_API_KEYS"}:
                keys.extend([item.strip() for item in value.split(",") if item.strip()])

    env_value = os.getenv("TOUR_API_KEYS") or os.getenv("TOUR_API_KEY")
    if env_value:
        keys.extend([item.strip() for item in env_value.split(",") if item.strip()])

    deduped = list(dict.fromkeys(keys))
    if not deduped:
        raise EnvironmentError("Configure TOUR_API_KEY or TOUR_API_KEYS before collecting TourAPI details.")
    return tuple(deduped)


class TourAPIClient:
    def __init__(self, config: TourAPIConfig, session: HttpSession | None = None) -> None:
        if not config.service_keys:
            raise ValueError("At least one TourAPI service key is required.")
        self.config = config
        self.session = session or requests.Session()
        self.current_key_index = 0

    def request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for _ in range(len(self.config.service_keys)):
            for attempt in range(self.config.max_retries + 1):
                if self.config.request_delay_seconds > 0:
                    time.sleep(self.config.request_delay_seconds)
                try:
                    return self._request_once(endpoint, params)
                except TourAPIError as exc:
                    last_error = exc
                    if _is_quota_error(exc.code, exc.message) and self._rotate_key():
                        break
                    if _is_permanent_error(exc.code):
                        raise
                    if attempt >= self.config.max_retries:
                        raise
                    time.sleep(min(2 * (attempt + 1), 10))
                except requests.RequestException as exc:
                    last_error = TourAPIError("REQUEST_ERROR", exc.__class__.__name__)
                    if attempt >= self.config.max_retries:
                        raise last_error
                    time.sleep(min(2 * (attempt + 1), 10))
        if last_error:
            raise last_error
        raise RuntimeError("Unreachable TourAPI retry state.")

    def _request_once(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        request_params.update(
            {
                "serviceKey": self.config.service_keys[self.current_key_index],
                "MobileOS": self.config.mobile_os,
                "MobileApp": self.config.mobile_app,
                "_type": "json",
            }
        )
        response = self.session.get(
            f"{self.config.base_url}/{endpoint}",
            params=request_params,
            timeout=self.config.timeout_seconds,
        )
        status_code = getattr(response, "status_code", 200)
        if status_code == 429:
            raise TourAPIError("429", "TOO_MANY_REQUESTS")
        if status_code >= 400:
            raise TourAPIError(str(status_code), "HTTP_ERROR")
        response.raise_for_status()
        text = getattr(response, "text", "")
        content_type = getattr(response, "headers", {}).get("Content-Type", "")
        if "xml" in content_type.lower() or text.strip().startswith("<"):
            raise _xml_error(text)

        payload = response.json()
        header = payload.get("response", {}).get("header", {})
        result_code = str(header.get("resultCode", "0000"))
        result_message = str(header.get("resultMsg", "OK"))
        if result_code not in {"0000", "00", "OK"}:
            raise TourAPIError(result_code, result_message)
        return payload

    def _rotate_key(self) -> bool:
        if self.current_key_index + 1 >= len(self.config.service_keys):
            return False
        self.current_key_index += 1
        return True


def collect_city_detail(
    city_list_path: Path,
    output_dir: Path,
    detail_cache_dir: Path,
    client: TourAPIClient,
    overwrite: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    city_payload = _read_json_object(city_list_path)
    meta = dict(city_payload.get("meta") or {})
    city_name_en = str(meta.get("city_name_en") or city_list_path.stem.replace("_filtered", ""))
    output_path = output_dir / f"{_safe_filename(city_name_en)}.json"
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path} (use --overwrite)")

    output_dir.mkdir(parents=True, exist_ok=True)
    detail_cache_dir.mkdir(parents=True, exist_ok=True)

    attractions = _record_list(city_payload.get("attractions"))
    festivals = _record_list(city_payload.get("festivals"))
    if limit is not None:
        attractions, festivals = _limit_records(attractions, festivals, limit)

    collected_attractions = [
        _attach_live_detail(item, detail_cache_dir, client)
        for item in attractions
    ]
    collected_festivals = [
        _attach_live_detail(item, detail_cache_dir, client)
        for item in festivals
    ]

    result = {
        "meta": meta,
        "attractions_count_filtered": city_payload.get("attractions_count_filtered", len(collected_attractions)),
        "festivals_count_filtered": city_payload.get("festivals_count_filtered", len(collected_festivals)),
        "attractions": [_enrich_item_status(item) for item in collected_attractions],
        "festivals": [_enrich_item_status(item) for item in collected_festivals],
    }

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def fetch_detail(client: TourAPIClient, content_id: str, content_type_id: str) -> dict[str, Any]:
    common_payload = client.request("detailCommon2", {"contentId": content_id})
    intro_payload = client.request("detailIntro2", {"contentId": content_id, "contentTypeId": content_type_id})
    return {
        "common": _first_item(common_payload),
        "intro": _first_item(intro_payload),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        service_keys = load_service_keys(args.env_file)
        client = TourAPIClient(TourAPIConfig(service_keys=service_keys))
        result = collect_city_detail(
            city_list_path=args.input,
            output_dir=args.output_dir,
            detail_cache_dir=args.detail_cache_dir,
            client=client,
            overwrite=args.overwrite,
            limit=args.limit,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    city_name = result.get("meta", {}).get("city_name_en") or args.input.stem
    print(
        f"[INFO] collected {city_name}: "
        f"{len(result['attractions'])} attractions, {len(result['festivals'])} festivals"
    )
    return 0


def _attach_live_detail(item: dict[str, Any], detail_cache_dir: Path, client: TourAPIClient) -> dict[str, Any]:
    content_id = str(item.get("contentid") or item.get("contentId") or "").strip()
    content_type_id = str(item.get("contenttypeid") or item.get("contentTypeId") or "").strip()
    enriched = dict(item)
    if not content_id:
        enriched["detail"] = {"common": {}, "intro": {}}
        return enriched

    cache_path = detail_cache_dir / f"{content_id}.json"
    if cache_path.exists():
        detail = _read_json_object(cache_path)
    else:
        detail = fetch_detail(client, content_id, content_type_id)
        cache_path.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(random.uniform(0.1, 0.3))
    enriched["detail"] = detail
    return enriched


def _first_item(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("response", {}).get("body", {}).get("items", {})
    item = items.get("item") if isinstance(items, dict) else {}
    if isinstance(item, list):
        return item[0] if item and isinstance(item[0], dict) else {}
    return item if isinstance(item, dict) else {}


def _xml_error(text: str) -> TourAPIError:
    code_match = re.search(r"<(?:returnReasonCode|resultCode|errMsg)>(.*?)</", text)
    message_match = re.search(r"<(?:returnAuthMsg|resultMsg|returnReasonMsg)>(.*?)</", text)
    code = code_match.group(1) if code_match else "XML_ERROR"
    message = message_match.group(1) if message_match else text[:200]
    return TourAPIError(code, message)


def _is_quota_error(code: str, message: str) -> bool:
    code_text = str(code).strip()
    message_text = str(message).upper()
    return code_text in {"22", "0022", "429"} or "LIMIT" in message_text or "EXCEEDED" in message_text


def _is_permanent_error(code: str) -> bool:
    return str(code).strip() in {"10", "0010", "11", "0011", "12", "0012", "30", "0030", "31", "0031", "32", "0032"}


def _limit_records(
    attractions: list[dict[str, Any]],
    festivals: list[dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if limit <= 0:
        return [], []
    if len(attractions) >= limit:
        return attractions[:limit], []
    remaining = limit - len(attractions)
    return attractions, festivals[:remaining]


def _record_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _safe_filename(value: str) -> str:
    normalized = value.lower().strip().replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_\-]", "", normalized)
    return normalized or "city"


if __name__ == "__main__":
    raise SystemExit(main())
