"""Bedrock 축제 6대 테마 재분류 모듈.

Festival-specific Bedrock theme reclassification module.
Responsible for classifying festival items into Lovv 6대 테마
based on actual content rather than the broad lclsSystm3 codes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL_ID = "openai.gpt-oss-120b-1:0"
PROMPT_VERSION = "festival-theme-v1"
SCHEMA_VERSION = "1"
MAX_RETRIES = 2
MIN_TEXT_LENGTH = 30  # Minimum text length to attempt classification

# Lovv 6대 테마
LOVV_THEMES = frozenset({
    "바다·해안",
    "자연·트레킹",
    "미식·노포",
    "역사·전통",
    "예술·감성",
    "온천·휴양",
})

# ---------------------------------------------------------------------------
# Prompt Field Boundary Constants (Req 7.2, 7.3)
# ---------------------------------------------------------------------------

ALLOWED_FESTIVAL_PROMPT_FIELDS: tuple[str, ...] = (
    "entity_type",
    "content_id",
    "title",
    "description",
    "program",
    "subevent",
    "venue",
    "playtime",
    "lcls_systm3",
    "source_theme",
)

FORBIDDEN_FESTIVAL_PROMPT_FIELDS: frozenset[str] = frozenset({
    "PK",
    "SK",
    "phone",
    "tel",
    "source_key",
    "raw_s3_uri",
    "festival_theme_classification",
})

# Fields used to compute festival input_hash (Req 8.6)
FESTIVAL_HASH_FIELDS = [
    "content_id",
    "description",
    "entity_type",
    "lcls_systm3",
    "playtime",
    "program",
    "source_theme",
    "subevent",
    "title",
    "venue",
]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_festival_prompt(item: dict[str, Any]) -> str:
    """Build a structured prompt for festival theme classification.

    Constructs a prompt using only allowed fields from the festival item.
    Forbidden fields (PK, SK, phone, tel, source_key, raw_s3_uri,
    festival_theme_classification) are never included regardless of their
    presence in the item.

    The prompt instructs the model to classify the festival into one of
    Lovv 6대 테마, with rules about side programs to prevent
    misclassification based solely on ancillary activities.

    Args:
        item: DynamoDB festival item dict.

    Returns:
        Formatted prompt string for Bedrock model input.
    """
    # Build the festival info section from allowed fields only
    info_lines: list[str] = []
    for field_name in ALLOWED_FESTIVAL_PROMPT_FIELDS:
        value = item.get(field_name)
        if value is None:
            continue
        # Convert lists to comma-separated string
        if isinstance(value, list):
            str_value = ", ".join(str(v) for v in value)
        else:
            str_value = str(value)
        # Skip empty string values
        if not str_value.strip():
            continue
        info_lines.append(f"{field_name}: {str_value}")

    festival_info = "\n".join(info_lines)

    prompt = (
        "다음 축제 정보를 분석하여 Lovv 6대 테마로 분류하세요.\n"
        "\n"
        "[축제 정보]\n"
        f"{festival_info}\n"
        "\n"
        "[Lovv 6대 테마]\n"
        "- 바다·해안\n"
        "- 자연·트레킹\n"
        "- 미식·노포\n"
        "- 역사·전통\n"
        "- 예술·감성\n"
        "- 온천·휴양\n"
        "\n"
        "[분류 규칙]\n"
        "- primary_theme: 정확히 1개 선택\n"
        "- theme_tags: 1~3개 선택 (primary_theme 포함)\n"
        "- 부대 먹거리만으로 미식·노포 선택 금지\n"
        "- 부대 공연만으로 예술·감성 선택 금지\n"
        "- 바다 관련 장소/키워드 없이 물놀이만으로 바다·해안 선택 금지\n"
        "\n"
        '[출력 형식] JSON:\n'
        '{"primary_theme": "...", "theme_tags": ["...", "..."]}'
    )

    return prompt


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ThemeClassificationResult:
    """Result of a single festival theme classification."""

    status: Literal["succeeded", "failed", "review_required"]
    primary_theme: str | None
    theme_tags: list[str]
    festival_theme_classification: dict[str, Any]


@dataclass
class ClassificationBatchResult:
    """Aggregated result of a batch classification run."""

    success_count: int = 0
    failure_count: int = 0
    review_required_count: int = 0
    failed_items: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core utility functions
# ---------------------------------------------------------------------------


def compute_festival_input_hash(item: dict[str, Any]) -> str:
    """Compute SHA-256 hash of normalized festival input fields.

    Fields are sorted alphabetically by key. Each value is converted to
    a string with whitespace removed and lowercased before hashing.
    The resulting hash is prefixed with "sha256:".

    Args:
        item: DynamoDB festival item dict.

    Returns:
        Hash string in format "sha256:{hex_digest}".
    """
    parts: list[str] = []
    for key in sorted(FESTIVAL_HASH_FIELDS):
        raw_value = item.get(key)
        if raw_value is None:
            normalized = ""
        elif isinstance(raw_value, list):
            normalized = "".join(str(v) for v in raw_value).replace(" ", "").lower()
        else:
            normalized = str(raw_value).replace(" ", "").lower()
        parts.append(normalized)

    combined = "".join(parts)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class ThemeValidationError(Exception):
    """Raised when festival theme response fails validation."""

    pass


def validate_festival_theme_output(response: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize Bedrock festival theme classification response.

    Validation logic:
    1. Extract primary_theme; if not in LOVV_THEMES → raise ThemeValidationError
    2. Extract theme_tags list; filter to only LOVV_THEMES values
    3. Limit theme_tags to max 3
    4. If primary_theme not in theme_tags → insert at index 0
    5. If len(theme_tags) > 3 after insertion → truncate to 3
    6. If len(theme_tags) == 0 → raise ThemeValidationError
    7. Return validated dict

    Args:
        response: Parsed JSON response with primary_theme and theme_tags.

    Returns:
        Validated dict with primary_theme (str) and theme_tags (list[str]).

    Raises:
        ThemeValidationError: If primary_theme is invalid or no valid themes remain.
    """
    # Step 1: Extract and validate primary_theme
    primary_theme = response.get("primary_theme")
    if primary_theme not in LOVV_THEMES:
        raise ThemeValidationError(
            f"primary_theme '{primary_theme}' is not a valid Lovv 6대 테마. "
            f"Valid themes: {sorted(LOVV_THEMES)}"
        )

    # Step 2: Extract theme_tags and filter to valid themes only
    raw_tags = response.get("theme_tags")
    if not isinstance(raw_tags, list):
        raw_tags = []

    theme_tags = [tag for tag in raw_tags if tag in LOVV_THEMES]

    # Step 3: Limit to max 3
    theme_tags = theme_tags[:3]

    # Step 4: Auto-insert primary_theme at position 0 if missing
    if primary_theme not in theme_tags:
        theme_tags.insert(0, primary_theme)

    # Step 5: Truncate to 3 after insertion
    theme_tags = theme_tags[:3]

    # Step 6: If no valid themes remain, raise error
    if len(theme_tags) == 0:
        raise ThemeValidationError(
            "No valid themes remain after filtering. "
            "At least 1 valid Lovv 6대 테마 is required in theme_tags."
        )

    # Step 7: Return validated result
    return {"primary_theme": primary_theme, "theme_tags": theme_tags}


def should_skip_classification(
    item: dict[str, Any],
    *,
    prompt_version: str = PROMPT_VERSION,
    model_id: str = DEFAULT_MODEL_ID,
) -> bool:
    """Determine whether to skip Bedrock classification for a festival item.

    Skip conditions (all must be true):
    1. Item has festival_theme_classification with status="succeeded"
    2. input_hash matches current computed hash
    3. prompt_version matches
    4. model_id matches

    Args:
        item: DynamoDB festival item dict.
        prompt_version: Current prompt version string.
        model_id: Current Bedrock model ID.

    Returns:
        True if classification should be skipped (no changes detected).
    """
    classification = item.get("festival_theme_classification")
    if not isinstance(classification, dict):
        return False

    # Condition 1: previous status must be "succeeded"
    if classification.get("status") != "succeeded":
        return False

    # Condition 2: input_hash must match
    current_hash = compute_festival_input_hash(item)
    if classification.get("input_hash") != current_hash:
        return False

    # Condition 3: prompt_version must match
    if classification.get("prompt_version") != prompt_version:
        return False

    # Condition 4: model_id must match
    if classification.get("model_id") != model_id:
        return False

    return True


# ---------------------------------------------------------------------------
# Single item classification
# ---------------------------------------------------------------------------

# Text fields used for sufficiency check (Req 8.2/7.12)
_TEXT_SUFFICIENCY_FIELDS = ("description", "program", "subevent")


def _has_sufficient_text(item: dict[str, Any]) -> bool:
    """Check whether the item has at least one text field >= MIN_TEXT_LENGTH.

    Returns True if at least one of description, program, subevent has
    non-None text of MIN_TEXT_LENGTH (30) characters or more.
    """
    for field_name in _TEXT_SUFFICIENCY_FIELDS:
        value = item.get(field_name)
        if value and isinstance(value, str) and len(value.strip()) >= MIN_TEXT_LENGTH:
            return True
    return False


def _parse_bedrock_response_json(response: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON from Bedrock converse API response.

    Extracts text from response["output"]["message"]["content"][0]["text"],
    strips markdown code fences if present, and parses as JSON.

    Raises:
        ValueError: If response does not contain valid JSON.
    """
    content = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    ).strip()

    if not text:
        raise ValueError("Bedrock response did not contain text")

    # Strip markdown code fences if present
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE
    )
    if fenced:
        text = fenced.group(1)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bedrock response was not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Bedrock response must be a JSON object")

    return payload


def _categorize_error(exc: Exception) -> tuple[str, bool]:
    """Categorize an exception into an error_code and whether it's retryable.

    Returns:
        Tuple of (error_code, should_retry).
    """
    exc_type = type(exc).__name__
    exc_str = str(exc)

    if "ThrottlingException" in exc_type or "ThrottlingException" in exc_str:
        return "throttling", True
    if "ModelTimeoutException" in exc_type or "timeout" in exc_str.lower():
        return "timeout", True
    if isinstance(exc, (ValueError, ThemeValidationError)):
        return "validation_error", False
    # Generic service/model error
    return "model_error", True


def classify_festival_theme(
    client: Any,  # Bedrock runtime client
    item: dict[str, Any],
    *,
    model_id: str = DEFAULT_MODEL_ID,
    prompt_version: str = PROMPT_VERSION,
) -> ThemeClassificationResult:
    """단일 축제 item에 대한 테마 재분류 실행.

    Steps:
    1. Check entity_type == "festival", else return failed result
    2. Check should_skip_classification() → preserve existing if True
    3. Check text sufficiency → review_required if insufficient
    4. Build prompt via build_festival_prompt(item)
    5. Call Bedrock converse API with retry (MAX_RETRIES=2, exponential backoff)
    6. Validate via validate_festival_theme_output()
    7. On success: build festival_theme_classification with status=succeeded
    8. On failure: status=failed, preserve existing theme/theme_tags

    Args:
        client: Bedrock runtime client (boto3 bedrock-runtime client).
        item: DynamoDB festival item dict.
        model_id: Bedrock model identifier.
        prompt_version: Current prompt version string.

    Returns:
        ThemeClassificationResult with classification outcome.
    """
    # Step 1: entity_type filter
    if item.get("entity_type") != "festival":
        return ThemeClassificationResult(
            status="failed",
            primary_theme=None,
            theme_tags=[],
            festival_theme_classification={
                "status": "failed",
                "error_code": "invalid_entity_type",
            },
        )

    # Step 2: Skip if already classified with same inputs
    if should_skip_classification(item, prompt_version=prompt_version, model_id=model_id):
        existing_classification = item.get("festival_theme_classification", {})
        return ThemeClassificationResult(
            status="succeeded",
            primary_theme=item.get("theme"),
            theme_tags=item.get("theme_tags", []),
            festival_theme_classification=existing_classification,
        )

    # Step 3: Text sufficiency check (Req 8.2 / 7.12)
    if not _has_sufficient_text(item):
        input_hash = compute_festival_input_hash(item)
        return ThemeClassificationResult(
            status="review_required",
            primary_theme=None,
            theme_tags=[],
            festival_theme_classification={
                "status": "review_required",
                "model_id": model_id,
                "prompt_version": prompt_version,
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "input_hash": input_hash,
            },
        )

    # Step 4: Build prompt
    prompt_text = build_festival_prompt(item)

    # Step 5: Call Bedrock converse API with retry
    last_error_code = "model_error"
    last_exception: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.converse(
                modelId=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt_text}],
                    }
                ],
            )

            # Parse JSON from response
            parsed = _parse_bedrock_response_json(response)

            # Step 6: Validate
            validated = validate_festival_theme_output(parsed)

            # Step 7: Success - build history object (Req 8.1)
            input_hash = compute_festival_input_hash(item)
            classification_history = {
                "status": "succeeded",
                "model_id": model_id,
                "prompt_version": prompt_version,
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "input_hash": input_hash,
            }

            return ThemeClassificationResult(
                status="succeeded",
                primary_theme=validated["primary_theme"],
                theme_tags=validated["theme_tags"],
                festival_theme_classification=classification_history,
            )

        except Exception as exc:
            error_code, should_retry = _categorize_error(exc)
            last_error_code = error_code
            last_exception = exc

            # Don't retry validation errors
            if not should_retry:
                break

            # If we have retries left, sleep with exponential backoff
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)  # 1s, 2s
            else:
                # All retries exhausted
                break

    # Step 8: Failure - preserve existing theme/theme_tags (Req 8.3)
    # Do NOT auto-promote source_theme to theme
    input_hash = compute_festival_input_hash(item)
    classification_history = {
        "status": "failed",
        "error_code": last_error_code,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "schema_version": SCHEMA_VERSION,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "input_hash": input_hash,
    }

    logger.warning(
        "Festival theme classification failed: content_id=%s, error_code=%s, error=%s",
        item.get("content_id", "unknown"),
        last_error_code,
        str(last_exception),
    )

    return ThemeClassificationResult(
        status="failed",
        primary_theme=None,
        theme_tags=[],
        festival_theme_classification=classification_history,
    )


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def run_classification_batch(
    client: Any,  # Bedrock runtime client
    items: list[dict[str, Any]],
    *,
    model_id: str = DEFAULT_MODEL_ID,
    prompt_version: str = PROMPT_VERSION,
    batch_size: int = 100,
) -> ClassificationBatchResult:
    """배치 단위 재분류.

    Processes festival items in batches, calling classify_festival_theme
    for each item. Failures do not halt the batch - processing continues
    with remaining items.

    Batch splitting logic:
    - If len(items) > 500: split into batches of batch_size (default 100)
    - If len(items) <= 500: process as a single batch

    Args:
        client: Bedrock runtime client for API calls.
        items: List of DynamoDB festival item dicts to classify.
        model_id: Bedrock model identifier.
        prompt_version: Current prompt version string.
        batch_size: Maximum items per batch when splitting (default 100).

    Returns:
        ClassificationBatchResult with aggregated success/failure/review counts.
    """
    result = ClassificationBatchResult()

    # Determine batches
    if len(items) > 500:
        batches = [
            items[i : i + batch_size] for i in range(0, len(items), batch_size)
        ]
    else:
        batches = [items]

    # Process each batch
    for batch in batches:
        for item in batch:
            try:
                classification_result = classify_festival_theme(
                    client,
                    item,
                    model_id=model_id,
                    prompt_version=prompt_version,
                )

                if classification_result.status == "succeeded":
                    result.success_count += 1
                elif classification_result.status == "review_required":
                    result.review_required_count += 1
                elif classification_result.status == "failed":
                    result.failure_count += 1
                    content_id = item.get("content_id", "unknown")
                    error_code = classification_result.festival_theme_classification.get(
                        "error_code", "unknown"
                    )
                    result.failed_items.append(
                        {"content_id": content_id, "error_code": error_code}
                    )
                    logger.warning(
                        "Festival classification failed: content_id=%s, error_code=%s",
                        content_id,
                        error_code,
                    )
            except Exception as exc:
                result.failure_count += 1
                content_id = item.get("content_id", "unknown")
                result.failed_items.append(
                    {"content_id": content_id, "error_code": "unexpected_error"}
                )
                logger.warning(
                    "Festival classification unexpected error: content_id=%s, error=%s",
                    content_id,
                    str(exc),
                )

    return result
