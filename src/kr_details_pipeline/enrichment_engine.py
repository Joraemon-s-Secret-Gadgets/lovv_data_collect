"""Bedrock attraction metadata enrichment engine.

Core interfaces, dataclasses, taxonomy constants, and hash/skip logic
for the attraction enrichment pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when Bedrock response fails schema validation."""
    pass


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL_ID = "openai.gpt-oss-120b-1:0"
PROMPT_VERSION = "attraction-metadata-v2"
MAX_PROMPT_LENGTH = 12_000
MAX_RETRIES = 2

# ---------------------------------------------------------------------------
# Prompt Field Boundary Constants
# ---------------------------------------------------------------------------

ALLOWED_PROMPT_FIELDS: set[str] = {
    "entity_type",
    "content_id",
    "title",
    "description",
    "theme",
    "theme_tags",
    "experience_guide",
    "opening_hours",
    "closed_days",
    "parking",
    "address",
}

FORBIDDEN_PROMPT_FIELDS: set[str] = {
    "PK",
    "SK",
    "source_key",
    "raw_s3_uri",
    "classification_source",
    "classification_mapping_version",
    "metadata_enrichment",
}

# ---------------------------------------------------------------------------
# Canonical Taxonomy Constants
# ---------------------------------------------------------------------------

VIBE_TAGS = frozenset({
    "romantic", "nostalgic", "cozy", "meditative", "refreshing", "inspiring",
    "calm", "peaceful", "healing", "relaxing", "serene", "artistic", "traditional", "rustic",
    "open_view", "panoramic_view", "ocean_view", "mountain_view", "river_view",
    "lake_view", "forest_view", "sunrise_view", "sunset_view", "night_view",
    "flower_view", "autumn_leaves", "snow_view",
    "local", "authentic", "regional_culture", "village_life", "craft",
    "old_restaurant", "local_market", "small_town", "rural", "retro", "community_based",
})

EXPERIENCE_TAGS = frozenset({
    "photo_spot", "picnic", "drive_course", "walking", "slow_travel",
    "cultural_experience", "nature_observation", "history_learning",
    "market_tour", "hands_on_experience",
})

COMPANION_FIT = frozenset({
    "family", "kids", "couple", "solo", "pet", "parents", "seniors",
})

INDOOR_OUTDOOR = frozenset({"indoor", "outdoor", "mixed", "unknown"})

# Fields used to compute the input hash for attraction items (sorted alphabetically)
_HASH_FIELDS = [
    "address", "closed_days", "description", "experience_guide",
    "opening_hours", "parking", "theme", "theme_tags", "title",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EnrichmentResult:
    """Result of a single attraction enrichment operation."""

    status: Literal["succeeded", "failed", "skipped"]
    indoor_outdoor: str | None = None
    vibe_tags: list[str] = field(default_factory=list)
    experience_tags: list[str] = field(default_factory=list)
    companion_fit: list[str] = field(default_factory=list)
    metadata_enrichment: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchResult:
    """Aggregated result of a batch enrichment run."""

    success_count: int = 0
    failure_count: int = 0
    skip_count: int = 0
    failed_items: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------

def compute_input_hash(item: dict[str, Any]) -> str:
    """Compute SHA-256 hash of sorted, normalized attraction fields.

    Fields are sorted alphabetically by key. Each value is converted to a
    string with whitespace removed and lowercased before hashing.

    Returns:
        A string in the format ``sha256:<hex_digest>``.
    """
    parts: list[str] = []
    for key in _HASH_FIELDS:
        value = item.get(key, "")
        if value is None:
            value = ""
        # Convert lists (e.g. theme_tags) to JSON string for consistent hashing
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            value = str(value)
        # Normalize: remove whitespace, lowercase
        normalized = "".join(value.split()).lower()
        parts.append(normalized)

    concatenated = "".join(parts)
    digest = hashlib.sha256(concatenated.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# Skip logic (deduplication)
# ---------------------------------------------------------------------------

def should_skip_enrichment(
    item: dict[str, Any],
    *,
    model_id: str = DEFAULT_MODEL_ID,
    prompt_version: str = PROMPT_VERSION,
) -> bool:
    """Determine whether enrichment should be skipped for an item.

    Enrichment is skipped (returns True) when ALL of the following hold:
    - The item has a ``metadata_enrichment`` dict
    - ``metadata_enrichment.status`` is ``"succeeded"``
    - ``metadata_enrichment.input_hash`` matches the current computed hash
    - ``metadata_enrichment.prompt_version`` matches the current prompt version
    - ``metadata_enrichment.model_id`` matches the current model id

    In all other cases (no previous enrichment, previous failure/skip,
    or any parameter mismatch), returns False.
    """
    enrichment = item.get("metadata_enrichment")
    if not enrichment or not isinstance(enrichment, dict):
        return False

    # Only skip if the previous run succeeded
    if enrichment.get("status") != "succeeded":
        return False

    # Compute current input hash and compare
    current_hash = compute_input_hash(item)
    if enrichment.get("input_hash") != current_hash:
        return False

    if enrichment.get("prompt_version") != prompt_version:
        return False

    if enrichment.get("model_id") != model_id:
        return False

    return True


# ---------------------------------------------------------------------------
# Bedrock response validation
# ---------------------------------------------------------------------------

_ALLOWED_OUTPUT_FIELDS = frozenset({
    "indoor_outdoor", "vibe_tags", "experience_tags", "companion_fit",
})


def validate_extracted_metadata(response: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize Bedrock enrichment response.

    The function is strict about extra fields (raises ValidationError) but
    lenient about invalid tag values (silently removes them).

    Args:
        response: Parsed JSON response from Bedrock.

    Returns:
        Validated dict with only the 4 allowed fields:
        - indoor_outdoor: one of {indoor, outdoor, mixed, unknown}
        - vibe_tags: list of canonical tags, max 5
        - experience_tags: list of canonical tags, max 3
        - companion_fit: list of canonical values, max 7

    Raises:
        ValidationError: If response contains fields beyond the 4 allowed.
    """
    # Check for extra fields (Req 3.4)
    extra_fields = set(response.keys()) - _ALLOWED_OUTPUT_FIELDS
    if extra_fields:
        raise ValidationError(
            f"Response contains disallowed fields: {sorted(extra_fields)}"
        )

    # Validate indoor_outdoor (Req 3.5)
    indoor_outdoor = response.get("indoor_outdoor", "unknown")
    if indoor_outdoor not in INDOOR_OUTDOOR:
        indoor_outdoor = "unknown"

    # Filter vibe_tags against canonical taxonomy, max 5 (Req 3.6, 3.9)
    raw_vibe_tags = response.get("vibe_tags", [])
    if not isinstance(raw_vibe_tags, list):
        raw_vibe_tags = []
    vibe_tags = [tag for tag in raw_vibe_tags if tag in VIBE_TAGS][:5]

    # Filter experience_tags against canonical taxonomy, max 3 (Req 3.7, 3.9)
    raw_experience_tags = response.get("experience_tags", [])
    if not isinstance(raw_experience_tags, list):
        raw_experience_tags = []
    experience_tags = [
        tag for tag in raw_experience_tags if tag in EXPERIENCE_TAGS
    ][:3]

    # Filter companion_fit against canonical values, max 7 (Req 3.8, 3.9)
    raw_companion_fit = response.get("companion_fit", [])
    if not isinstance(raw_companion_fit, list):
        raw_companion_fit = []
    companion_fit = [
        val for val in raw_companion_fit if val in COMPANION_FIT
    ][:7]

    return {
        "indoor_outdoor": indoor_outdoor,
        "vibe_tags": vibe_tags,
        "experience_tags": experience_tags,
        "companion_fit": companion_fit,
    }


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

# Field order for prompt output (entity_type and content_id first, then others)
_PROMPT_FIELD_ORDER = [
    "entity_type",
    "content_id",
    "title",
    "description",
    "theme",
    "theme_tags",
    "experience_guide",
    "opening_hours",
    "closed_days",
    "parking",
    "address",
]

_PROMPT_HEADER = "다음 관광지 정보를 분석하여 메타데이터를 추출하세요."

_PROMPT_OUTPUT_FORMAT = """[출력 형식] JSON으로 응답하세요:
{
  "indoor_outdoor": "indoor|outdoor|mixed|unknown",
  "vibe_tags": ["tag1", "tag2", ...],
  "experience_tags": ["tag1", ...],
  "companion_fit": ["type1", ...]
}"""

_PROMPT_TAXONOMY = """[허용 태그 목록]
indoor_outdoor: indoor, outdoor, mixed, unknown

vibe_tags (최대 5개):
romantic, nostalgic, cozy, meditative, refreshing, inspiring, calm, peaceful, healing, relaxing, serene, artistic, traditional, rustic, open_view, panoramic_view, ocean_view, mountain_view, river_view, lake_view, forest_view, sunrise_view, sunset_view, night_view, flower_view, autumn_leaves, snow_view, local, authentic, regional_culture, village_life, craft, old_restaurant, local_market, small_town, rural, retro, community_based

experience_tags (최대 3개):
photo_spot, picnic, drive_course, walking, slow_travel, cultural_experience, nature_observation, history_learning, market_tour, hands_on_experience

companion_fit (최대 7개):
family, kids, couple, solo, pet, parents, seniors"""


def build_extraction_prompt(item: dict[str, Any]) -> str:
    """Build a structured prompt for Bedrock attraction metadata extraction.

    Only allowed fields are included in the prompt. Forbidden fields are
    excluded regardless of their presence in the item. If the assembled
    prompt exceeds MAX_PROMPT_LENGTH (12,000 chars), the description field
    is truncated first to fit within the limit.

    Args:
        item: A DynamoDB attraction item dict.

    Returns:
        A prompt string of at most MAX_PROMPT_LENGTH characters.
    """
    # Build the info section from allowed fields only
    info_lines: list[str] = []
    for field_name in _PROMPT_FIELD_ORDER:
        if field_name in FORBIDDEN_PROMPT_FIELDS:
            continue
        value = item.get(field_name)
        if value is None:
            continue
        # Convert lists to comma-separated string
        if isinstance(value, list):
            value_str = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value_str = json.dumps(value, ensure_ascii=False)
        else:
            value_str = str(value)
        if not value_str:
            continue
        info_lines.append(f"{field_name}: {value_str}")

    info_section = "\n".join(info_lines)

    # Assemble the full prompt
    prompt = (
        f"{_PROMPT_HEADER}\n\n"
        f"[관광지 정보]\n"
        f"{info_section}\n\n"
        f"{_PROMPT_TAXONOMY}\n\n"
        f"{_PROMPT_OUTPUT_FORMAT}"
    )

    # Enforce character limit by truncating description first
    if len(prompt) > MAX_PROMPT_LENGTH:
        # Calculate how much we need to trim
        overage = len(prompt) - MAX_PROMPT_LENGTH
        # Find and truncate the description value in info_lines
        description_value = item.get("description", "")
        if description_value and isinstance(description_value, str):
            desc_prefix = "description: "
            # Rebuild without description to see base size
            info_lines_no_desc = [
                line for line in info_lines if not line.startswith(desc_prefix)
            ]
            info_section_no_desc = "\n".join(info_lines_no_desc)
            base_prompt = (
                f"{_PROMPT_HEADER}\n\n"
                f"[관광지 정보]\n"
                f"{info_section_no_desc}\n\n"
                f"{_PROMPT_TAXONOMY}\n\n"
                f"{_PROMPT_OUTPUT_FORMAT}"
            )
            # Calculate available space for description line
            available = MAX_PROMPT_LENGTH - len(base_prompt) - len("\n") - len(desc_prefix)
            if available > 0:
                truncated_desc = description_value[:available]
                # Find the position of description in the field order and rebuild
                new_info_lines: list[str] = []
                for line in info_lines:
                    if line.startswith(desc_prefix):
                        new_info_lines.append(f"{desc_prefix}{truncated_desc}")
                    else:
                        new_info_lines.append(line)
                info_section = "\n".join(new_info_lines)
            else:
                # No room for description at all, remove it
                info_section = info_section_no_desc

            prompt = (
                f"{_PROMPT_HEADER}\n\n"
                f"[관광지 정보]\n"
                f"{info_section}\n\n"
                f"{_PROMPT_TAXONOMY}\n\n"
                f"{_PROMPT_OUTPUT_FORMAT}"
            )

    # Final safety truncation (if still over after description truncation)
    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = prompt[:MAX_PROMPT_LENGTH]

    return prompt

# ---------------------------------------------------------------------------
# Enrichment execution
# ---------------------------------------------------------------------------

# Schema version for enrichment output
SCHEMA_VERSION = "1"

# Retry configuration
_RETRY_BASE_DELAY = 1.0  # seconds


def _categorize_error(error: ClientError) -> str:
    """Categorize a botocore ClientError into an enrichment error_code.

    Returns one of: "throttling", "timeout", "model_error".
    """
    error_code = error.response.get("Error", {}).get("Code", "")
    if "Throttling" in error_code or "TooManyRequests" in error_code:
        return "throttling"
    if "Timeout" in error_code or "ReadTimeout" in error_code:
        return "timeout"
    return "model_error"


def _is_retryable_error(error_code: str) -> bool:
    """Determine if the error_code warrants a retry."""
    return error_code in ("throttling", "timeout", "model_error")


def _all_outputs_empty_or_unknown(validated: dict[str, Any]) -> bool:
    """Check if all 4 output fields are unknown or empty.

    Returns True if:
    - indoor_outdoor is "unknown" or empty
    - vibe_tags is empty
    - experience_tags is empty
    - companion_fit is empty
    """
    io = validated.get("indoor_outdoor", "unknown")
    if io not in ("unknown", "", None):
        return False
    if validated.get("vibe_tags"):
        return False
    if validated.get("experience_tags"):
        return False
    if validated.get("companion_fit"):
        return False
    return True


def enrich_attraction(
    client: Any,
    item: dict[str, Any],
    *,
    model_id: str = DEFAULT_MODEL_ID,
    prompt_version: str = PROMPT_VERSION,
) -> EnrichmentResult:
    """Single attraction item enrichment via Bedrock converse API.

    This function:
    1. Checks entity_type == "attraction", else returns failed result
    2. Checks should_skip_enrichment() → returns skipped if True
    3. Builds prompt via build_extraction_prompt()
    4. Calls Bedrock converse API with retry loop (max MAX_RETRIES attempts)
    5. Parses JSON response, validates via validate_extracted_metadata()
    6. If all outputs are unknown/empty → status=skipped
    7. Builds metadata_enrichment dict with appropriate fields

    The function does NOT modify the item dict. It returns an EnrichmentResult
    that the caller can use to update DynamoDB.

    Args:
        client: Bedrock runtime client (must have .converse() method).
        item: DynamoDB attraction item dict.
        model_id: Bedrock model identifier.
        prompt_version: Version string for the prompt template.

    Returns:
        EnrichmentResult with status, extracted fields, and metadata_enrichment dict.
    """
    # Req 3.1: Only process entity_type="attraction"
    if item.get("entity_type") != "attraction":
        return EnrichmentResult(
            status="failed",
            metadata_enrichment={
                "status": "failed",
                "error_code": "model_error",
                "failed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )

    # Req 4.4, 4.5, 4.6: input_hash-based deduplication
    if should_skip_enrichment(item, model_id=model_id, prompt_version=prompt_version):
        return EnrichmentResult(
            status="skipped",
            metadata_enrichment=item.get("metadata_enrichment", {}),
        )

    # Build prompt (Req 3.2, 3.3, 3.11)
    prompt = build_extraction_prompt(item)
    input_hash = compute_input_hash(item)

    # Bedrock converse API call with retry (Req 3.10, 5.4)
    last_error_code: str | None = None
    for attempt in range(MAX_RETRIES + 1):  # initial + MAX_RETRIES retries
        try:
            response = client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
            )

            # Parse JSON from response
            # Handle models that return reasoningContent before text (e.g., GPT-OSS)
            content_parts = response["output"]["message"]["content"]
            raw_text = ""
            for part in content_parts:
                if "text" in part:
                    raw_text = part["text"].strip()
                    break
            if not raw_text:
                logger.warning(
                    "Empty text response for item %s",
                    item.get("content_id", "unknown"),
                )
                return EnrichmentResult(
                    status="failed",
                    metadata_enrichment={
                        "status": "failed",
                        "error_code": "validation_error",
                        "failed_at": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    },
                )
            # Strip markdown code fences if present (e.g. ```json ... ```)
            if raw_text.startswith("```"):
                import re
                fenced = re.fullmatch(
                    r"```(?:json)?\s*(.*?)\s*```", raw_text, flags=re.DOTALL | re.IGNORECASE
                )
                if fenced:
                    raw_text = fenced.group(1)
            try:
                parsed = json.loads(raw_text)
            except (json.JSONDecodeError, TypeError, KeyError) as exc:
                # JSON parse error → validation_error, no retry (Req 5.2)
                logger.warning(
                    "JSON parse error for item %s: %s",
                    item.get("content_id", "unknown"),
                    exc,
                )
                return EnrichmentResult(
                    status="failed",
                    metadata_enrichment={
                        "status": "failed",
                        "error_code": "validation_error",
                        "failed_at": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    },
                )

            # Validate extracted metadata (Req 3.4-3.9)
            try:
                validated = validate_extracted_metadata(parsed)
            except ValidationError as exc:
                # Schema validation failure → validation_error, no retry (Req 5.2)
                logger.warning(
                    "Validation error for item %s: %s",
                    item.get("content_id", "unknown"),
                    exc,
                )
                return EnrichmentResult(
                    status="failed",
                    metadata_enrichment={
                        "status": "failed",
                        "error_code": "validation_error",
                        "failed_at": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    },
                )

            # Req 4.3: If all outputs are unknown/empty → skipped
            if _all_outputs_empty_or_unknown(validated):
                return EnrichmentResult(
                    status="skipped",
                    metadata_enrichment={
                        "status": "skipped",
                        "model_id": model_id,
                        "prompt_version": prompt_version,
                        "schema_version": SCHEMA_VERSION,
                        "generated_at": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        "input_hash": input_hash,
                    },
                )

            # Req 4.1: Success → build metadata_enrichment with full history
            return EnrichmentResult(
                status="succeeded",
                indoor_outdoor=validated["indoor_outdoor"],
                vibe_tags=validated["vibe_tags"],
                experience_tags=validated["experience_tags"],
                companion_fit=validated["companion_fit"],
                metadata_enrichment={
                    "status": "succeeded",
                    "model_id": model_id,
                    "prompt_version": prompt_version,
                    "schema_version": SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "input_hash": input_hash,
                },
            )

        except ClientError as exc:
            last_error_code = _categorize_error(exc)
            logger.warning(
                "Bedrock call failed for item %s (attempt %d/%d): %s [%s]",
                item.get("content_id", "unknown"),
                attempt + 1,
                MAX_RETRIES + 1,
                exc,
                last_error_code,
            )

            # validation_error should not retry, but ClientError won't be one
            if not _is_retryable_error(last_error_code):
                break

            # If we have retries left, wait with exponential backoff
            if attempt < MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                time.sleep(delay)
            # Otherwise fall through to failure handling

    # Req 4.2, 5.4: All retries exhausted → mark as failed
    return EnrichmentResult(
        status="failed",
        metadata_enrichment={
            "status": "failed",
            "error_code": last_error_code or "model_error",
            "failed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )


# ---------------------------------------------------------------------------
# Batch enrichment
# ---------------------------------------------------------------------------


def run_enrichment_batch(
    client: Any,
    items: list[dict[str, Any]],
    *,
    model_id: str = DEFAULT_MODEL_ID,
    prompt_version: str = PROMPT_VERSION,
    batch_size: int = 100,
) -> BatchResult:
    """배치 단위 enrichment. 500건 초과 시 자동 분할.

    Args:
        client: Bedrock runtime client.
        items: List of DynamoDB attraction items to enrich.
        model_id: Bedrock model identifier.
        prompt_version: Prompt version string for tracking.
        batch_size: Maximum items per sub-batch (default 100).

    Returns:
        BatchResult with aggregated success/failure/skip counts.
    """
    result = BatchResult()

    # Determine batches: split into chunks of batch_size when > 500 items
    if len(items) > 500:
        batches = [
            items[i : i + batch_size]
            for i in range(0, len(items), batch_size)
        ]
    else:
        batches = [items]

    for batch in batches:
        for item in batch:
            try:
                enrichment_result = enrich_attraction(
                    client,
                    item,
                    model_id=model_id,
                    prompt_version=prompt_version,
                )

                if enrichment_result.status == "succeeded":
                    result.success_count += 1
                elif enrichment_result.status == "skipped":
                    result.skip_count += 1
                elif enrichment_result.status == "failed":
                    result.failure_count += 1
                    content_id = item.get("content_id", "unknown")
                    error_code = enrichment_result.metadata_enrichment.get(
                        "error_code", "unknown"
                    )
                    result.failed_items.append(
                        {"content_id": content_id, "error_code": error_code}
                    )
                    logger.warning(
                        "Enrichment failed for content_id=%s, error_code=%s",
                        content_id,
                        error_code,
                    )
            except Exception as exc:
                result.failure_count += 1
                content_id = item.get("content_id", "unknown")
                error_code = type(exc).__name__
                result.failed_items.append(
                    {"content_id": content_id, "error_code": error_code}
                )
                logger.warning(
                    "Enrichment exception for content_id=%s: %s",
                    content_id,
                    exc,
                )

    return result
