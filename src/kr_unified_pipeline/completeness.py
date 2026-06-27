"""
Completeness evaluator for unified preprocessing pipeline.

Evaluates CityRecord data completeness by checking required fields,
computing confidence scores, and determining review status.
Implements Requirements 3.1, 3.2, 3.3, 3.4, 3.5.
"""

from __future__ import annotations

from kr_unified_pipeline.models import CityRecord, CompletenessResult


# Status constants matching project convention (crawling/JP/models.py)
STATUS_COLLECTED = "collected"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_MISSING = "missing"


class CompletenessEvaluator:
    """Evaluates data completeness of CityRecord instances.

    Checks required fields for presence and validity, computes a
    data_confidence level, and flags records needing manual review.
    """

    REQUIRED_FIELDS: tuple[str, ...] = (
        "city_name_ko",
        "prefecture_id",
        "latitude",
        "longitude",
        "description",
    )

    def evaluate(self, record: CityRecord) -> CompletenessResult:
        """Evaluate a CityRecord's data completeness.

        Checks each required field for presence/validity and produces
        a CompletenessResult with confidence level, missing fields,
        per-field statuses, and review determination.

        Args:
            record: The CityRecord to evaluate.

        Returns:
            CompletenessResult with evaluation outcome.
        """
        missing_fields: list[str] = []
        field_statuses: dict[str, str] = {}
        review_reasons: list[str] = []

        # Requirement 3.1: Check presence of required fields
        # city_name_ko
        if not record.city_name_ko or not record.city_name_ko.strip():
            missing_fields.append("city_name_ko")
            field_statuses["city_name_ko"] = STATUS_MISSING
        else:
            field_statuses["city_name_ko"] = STATUS_COLLECTED

        # prefecture_id
        if not record.prefecture_id or not record.prefecture_id.strip():
            missing_fields.append("prefecture_id")
            field_statuses["prefecture_id"] = STATUS_MISSING
        else:
            field_statuses["prefecture_id"] = STATUS_COLLECTED

        # Requirement 3.2: Mark coordinates as STATUS_NEEDS_REVIEW when None
        if record.latitude is None:
            missing_fields.append("latitude")
            field_statuses["latitude"] = STATUS_NEEDS_REVIEW
            review_reasons.append("missing_coordinates")
        else:
            field_statuses["latitude"] = STATUS_COLLECTED

        if record.longitude is None:
            missing_fields.append("longitude")
            field_statuses["longitude"] = STATUS_NEEDS_REVIEW
            # Only add reason once for coordinate pair
            if "missing_coordinates" not in review_reasons:
                review_reasons.append("missing_coordinates")
        else:
            field_statuses["longitude"] = STATUS_COLLECTED

        # Requirement 3.3: Mark description as STATUS_NEEDS_REVIEW when empty/whitespace
        if not record.description or not record.description.strip():
            missing_fields.append("description")
            field_statuses["description"] = STATUS_NEEDS_REVIEW
            review_reasons.append("empty_description")
        else:
            field_statuses["description"] = STATUS_COLLECTED

        # Requirement 3.4: Compute confidence
        confidence = self.compute_confidence(record)

        # Requirement 3.5: Set needs_review when confidence is "low"
        needs_review = confidence == "low"
        if needs_review and "low_confidence" not in review_reasons:
            review_reasons.append("low_confidence")

        return CompletenessResult(
            data_confidence=confidence,
            missing_fields=tuple(missing_fields),
            field_statuses=field_statuses,
            needs_review=needs_review,
            review_reasons=tuple(review_reasons),
        )

    def compute_confidence(self, record: CityRecord) -> str:
        """Compute the data confidence level for a CityRecord.

        Requirement 3.4:
        - "high": all required fields are present and valid
        - "medium": at least city_name_ko and prefecture_id are present
        - "low": required fields (city_name_ko or prefecture_id) are missing

        Args:
            record: The CityRecord to assess.

        Returns:
            One of "high", "medium", or "low".
        """
        has_city_name = bool(record.city_name_ko and record.city_name_ko.strip())
        has_prefecture = bool(record.prefecture_id and record.prefecture_id.strip())
        has_latitude = record.latitude is not None
        has_longitude = record.longitude is not None
        has_description = bool(record.description and record.description.strip())

        # All required fields present and valid → high
        if has_city_name and has_prefecture and has_latitude and has_longitude and has_description:
            return "high"

        # At least city_name_ko and prefecture_id present → medium
        if has_city_name and has_prefecture:
            return "medium"

        # Otherwise → low
        return "low"
