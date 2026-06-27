"""
Review transition logic for the unified preprocessing pipeline.

Handles automatic status transitions for CityRecords based on
completeness evaluation results. Creates ReviewEntry objects for
the review manifest when records need attention.

Implements Requirements 4.1, 4.2, 4.3, 4.4, 4.5.
"""

from __future__ import annotations

from datetime import datetime, timezone

from kr_unified_pipeline.completeness import STATUS_COLLECTED, STATUS_NEEDS_REVIEW
from kr_unified_pipeline.models import CityRecord, CompletenessResult, ReviewEntry


class ReviewTransition:
    """Manages review state transitions for CityRecords.

    Applies completeness evaluation results to records by updating
    their field_status dict, generating review reasons, and creating
    ReviewEntry objects for the manifest.
    """

    def transition(self, record: CityRecord, result: CompletenessResult) -> None:
        """Transition a record to review status based on evaluation result.

        Updates the record's field_status dictionary with the specific
        fields requiring attention from the CompletenessResult.

        Requirement 4.1: Update field_status with specific fields requiring attention.
        Requirement 4.2: Generate review_reason indicating why the record was flagged.

        Args:
            record: The CityRecord to transition.
            result: The CompletenessResult from CompletenessEvaluator.
        """
        # Update record field_status with statuses from the evaluation result
        for field_name, status in result.field_statuses.items():
            record.field_status[field_name] = status

        # Also check image_url and mark if missing (Requirement 4.2: "no_image_url")
        if record.image_url is None or (isinstance(record.image_url, str) and not record.image_url.strip()):
            record.field_status["image_url"] = STATUS_NEEDS_REVIEW

        # Set overall data_confidence on the record
        record.data_confidence = result.data_confidence

    def upgrade_if_complete(self, record: CityRecord, result: CompletenessResult) -> None:
        """Restore record status to STATUS_COLLECTED when data is now complete.

        Requirement 4.4: When a subsequent pipeline run provides missing data,
        upgrade the record status from STATUS_NEEDS_REVIEW to STATUS_COLLECTED.

        Args:
            record: The CityRecord to potentially upgrade.
            result: The CompletenessResult from CompletenessEvaluator.
        """
        if not result.needs_review and not result.missing_fields:
            # All required fields are now present — upgrade all field statuses
            for field_name, status in result.field_statuses.items():
                record.field_status[field_name] = STATUS_COLLECTED

            # Also upgrade image_url status if image is now present
            if record.image_url and record.image_url.strip():
                record.field_status["image_url"] = STATUS_COLLECTED

            record.data_confidence = result.data_confidence

    def build_review_entry(self, record: CityRecord, result: CompletenessResult) -> ReviewEntry:
        """Create a ReviewEntry for the review manifest.

        Requirement 4.3, 4.5: Append flagged records to review manifest with
        city_id, city_name_ko, prefecture_id, missing_fields, review_reason,
        and ISO 8601 timestamp.

        Args:
            record: The CityRecord being flagged.
            result: The CompletenessResult with review details.

        Returns:
            A ReviewEntry populated with manifest data.
        """
        # Determine the primary review_reason (Requirement 4.2)
        review_reason = self._determine_review_reason(record, result)

        # Collect missing fields including image_url if applicable
        missing_fields = list(result.missing_fields)
        if record.image_url is None or (isinstance(record.image_url, str) and not record.image_url.strip()):
            if "image_url" not in missing_fields:
                missing_fields.append("image_url")

        return ReviewEntry(
            city_id=record.city_id,
            city_name_ko=record.city_name_ko,
            prefecture_id=record.prefecture_id,
            missing_fields=missing_fields,
            review_reason=review_reason,
            flagged_at=datetime.now(timezone.utc).isoformat(),
        )

    def _determine_review_reason(self, record: CityRecord, result: CompletenessResult) -> str:
        """Determine the primary review reason for a flagged record.

        Priority order:
        1. "missing_coordinates" — if latitude or longitude is missing
        2. "empty_description" — if description is empty/whitespace
        3. "no_image_url" — if image_url is None or empty

        Falls back to the first review_reason from the CompletenessResult
        if none of the specific checks match.

        Args:
            record: The CityRecord being evaluated.
            result: The CompletenessResult with review reasons.

        Returns:
            A string review reason identifier.
        """
        if "missing_coordinates" in result.review_reasons:
            return "missing_coordinates"
        if "empty_description" in result.review_reasons:
            return "empty_description"
        if record.image_url is None or (isinstance(record.image_url, str) and not record.image_url.strip()):
            return "no_image_url"
        # Fallback to first reason from evaluator
        if result.review_reasons:
            return result.review_reasons[0]
        return "unknown"
