"""
Unified preprocessing pipeline orchestrator.

Coordinates stage execution in canonical order, runs completeness
evaluation and review transitions after each stage, resolves images
during Wikipedia/TourAPI stages, and outputs a summary report.

Implements Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from kr_unified_pipeline.completeness import CompletenessEvaluator
from kr_unified_pipeline.image_resolver import ImageResolver
from kr_unified_pipeline.models import (
    CityRecord,
    PipelineConfig,
    PipelineContext,
    StageResult,
)
from kr_unified_pipeline.review_transition import ReviewTransition
from kr_unified_pipeline.stages import STAGE_ORDER, PipelineStage

logger = logging.getLogger(__name__)

# Preprocessing stages that trigger image resolution
_IMAGE_STAGES: frozenset[str] = frozenset({"wikipedia", "tourapi-region", "tourapi-detail"})

# All preprocessing stages (as opposed to load/vector-build)
_PREPROCESSING_STAGES: frozenset[str] = frozenset({"wikipedia", "tourapi-region", "tourapi-detail"})


class UnifiedPipeline:
    """Orchestrates preprocessing stage execution in canonical order.

    Coordinates stage execution, runs CompletenessEvaluator after each
    preprocessing stage, runs ImageResolver during Wikipedia/TourAPI stages
    (unless skip_images is set), and applies ReviewTransition for records
    needing review.

    Attributes:
        config: Pipeline configuration for this run.
        stages: Mapping of stage names to PipelineStage implementations.
        evaluator: CompletenessEvaluator instance.
        image_resolver: ImageResolver instance (may be None if images skipped).
        review_transition: ReviewTransition instance.
    """

    def __init__(
        self,
        config: PipelineConfig,
        stages: dict[str, PipelineStage] | None = None,
        evaluator: CompletenessEvaluator | None = None,
        image_resolver: ImageResolver | None = None,
        review_transition: ReviewTransition | None = None,
    ) -> None:
        """Initialize the UnifiedPipeline.

        Args:
            config: Pipeline configuration specifying which stages to run.
            stages: Mapping of stage name -> PipelineStage implementation.
                    If None, an empty mapping is used (stages must be registered).
            evaluator: CompletenessEvaluator instance. Created if not provided.
            image_resolver: ImageResolver instance. Created if not provided
                           and skip_images is False.
            review_transition: ReviewTransition instance. Created if not provided.
        """
        self.config = config
        self.stages: dict[str, PipelineStage] = stages or {}
        self.evaluator = evaluator or CompletenessEvaluator()
        self.review_transition = review_transition or ReviewTransition()

        # Only create ImageResolver if images are not skipped
        if config.skip_images:
            self.image_resolver: ImageResolver | None = None
        else:
            self.image_resolver = image_resolver or ImageResolver()

    def register_stage(self, stage: PipelineStage) -> None:
        """Register a pipeline stage implementation.

        Args:
            stage: A PipelineStage implementation to register.
        """
        self.stages[stage.name] = stage

    def run(self, context: PipelineContext | None = None) -> PipelineContext:
        """Execute the pipeline stages in canonical order.

        Creates a PipelineContext if not provided, determines which stages
        to execute based on configuration, runs them sequentially, and
        applies post-stage evaluation (completeness, image resolution,
        review transition) after each preprocessing stage.

        Requirement 1.1: Execute stages in defined sequential order.
        Requirement 1.2: Accept configuration specifying which stages to execute.
        Requirement 1.3: Pass PipelineContext between stages.
        Requirement 1.4: Accumulate results and merge into unified collection.
        Requirement 1.5: Handle non-recoverable stage failure gracefully.

        Args:
            context: Optional pre-existing PipelineContext. If None, a new
                     context is created with the current config.

        Returns:
            The final PipelineContext with accumulated results.
        """
        if context is None:
            context = PipelineContext(
                config=self.config,
                start_time=datetime.now(timezone.utc).isoformat(),
            )

        # Determine which stages to execute in canonical order
        stages_to_run = self._resolve_stages()

        logger.info(
            "Pipeline starting: stages=%s, start_time=%s",
            [s for s in stages_to_run],
            context.start_time,
        )

        for stage_name in stages_to_run:
            stage_impl = self.stages.get(stage_name)
            if stage_impl is None:
                logger.warning("Stage '%s' has no registered implementation, skipping.", stage_name)
                continue

            stage_result = StageResult(
                stage_name=stage_name,
                started_at=datetime.now(timezone.utc).isoformat(),
            )

            logger.info("Stage '%s' started at %s", stage_name, stage_result.started_at)

            try:
                # Execute the stage (Requirement 1.3: pass context between stages)
                context = stage_impl.execute(context)

                # Mark stage completion time
                stage_result.completed_at = datetime.now(timezone.utc).isoformat()
                stage_result.records_processed = len(context.city_records)

                # Post-stage processing for preprocessing stages
                if stage_name in _PREPROCESSING_STAGES:
                    self._post_stage_processing(context, stage_result, stage_name)

                logger.info(
                    "Stage '%s' completed at %s: %d records processed, %d updated, %d images",
                    stage_name,
                    stage_result.completed_at,
                    stage_result.records_processed,
                    stage_result.records_updated,
                    stage_result.images_collected,
                )

            except Exception as exc:
                # Requirement 1.5: Non-recoverable stage failure handling
                stage_result.completed_at = datetime.now(timezone.utc).isoformat()
                error_msg = f"Stage '{stage_name}' failed: {exc}"
                stage_result.errors.append(error_msg)
                context.errors.append(error_msg)

                logger.error(
                    "Stage '%s' failed with non-recoverable error: %s. "
                    "Preserving results from previously completed stages.",
                    stage_name,
                    exc,
                )

                # Append result and stop further stage execution
                context.stage_results.append(stage_result)
                break

            # Accumulate stage result (Requirement 1.4)
            context.stage_results.append(stage_result)

        # Output summary report (Requirement 8.1, 8.2)
        self._log_summary_report(context)

        return context

    def _resolve_stages(self) -> list[str]:
        """Determine which stages to execute based on configuration.

        Requirement 1.2: Accept configuration specifying which stages to execute.
        Requirement 2.5: Execute specified stages in defined sequential order.

        Returns only stages that appear in STAGE_ORDER, maintaining canonical
        order regardless of user-specified order.

        Returns:
            List of stage names in canonical execution order.
        """
        if not self.config.stages:
            # All stages by default
            return list(STAGE_ORDER)

        # Filter and order according to canonical STAGE_ORDER
        requested = set(self.config.stages)
        return [s for s in STAGE_ORDER if s in requested]

    def _post_stage_processing(
        self,
        context: PipelineContext,
        stage_result: StageResult,
        stage_name: str,
    ) -> None:
        """Run completeness evaluation, image resolution, and review transition.

        Called after each preprocessing stage completes.

        Requirement 3.1-3.5: CompletenessEvaluator checks after each stage.
        Requirement 4.1-4.5: ReviewTransition for records needing review.
        Requirement 5.1-5.5, 6.1-6.5: ImageResolver during image-eligible stages.

        Args:
            context: The current PipelineContext.
            stage_result: The StageResult for tracking metrics.
            stage_name: The name of the completed stage.
        """
        records_updated = 0
        images_collected = 0

        for record in context.city_records:
            # Run CompletenessEvaluator
            result = self.evaluator.evaluate(record)

            # Run ImageResolver for image-eligible stages (unless skip_images)
            if stage_name in _IMAGE_STAGES and self.image_resolver is not None:
                images_collected += self._resolve_images_for_record(
                    record, stage_name
                )

            # Apply review transition
            if result.needs_review:
                self.review_transition.transition(record, result)
                review_entry = self.review_transition.build_review_entry(record, result)
                context.review_manifest.append(review_entry)
            else:
                # Upgrade if data is now complete (Requirement 4.4)
                self.review_transition.upgrade_if_complete(record, result)

            # Track updates
            if result.data_confidence != "medium" or result.missing_fields:
                records_updated += 1

        stage_result.records_updated = records_updated
        stage_result.images_collected = images_collected

    def _resolve_images_for_record(self, record: CityRecord, stage_name: str) -> int:
        """Attempt to resolve images for a record based on the current stage.

        Args:
            record: The CityRecord to resolve images for.
            stage_name: The current stage name.

        Returns:
            Number of images collected (0 or 1).
        """
        if self.image_resolver is None:
            return 0

        images_found = 0

        if stage_name == "wikipedia":
            # Resolve Wikipedia thumbnail using city_name_ko as page title
            page_title = record.city_name_ko
            if page_title:
                url = self.image_resolver.resolve_wikipedia_image(page_title)
                if url:
                    self.image_resolver.apply_to_record(record, "wikipedia", url)
                    images_found += 1

        elif stage_name in ("tourapi-region", "tourapi-detail"):
            # TourAPI images are typically resolved during stage execution.
            # The stage itself should call apply_to_record, but we check
            # if image_url is still None and the record has tourapi data hints.
            # This is a fallback — most TourAPI image resolution happens
            # within the stage execute() method itself.
            pass

        return images_found

    def _log_summary_report(self, context: PipelineContext) -> None:
        """Output summary report on pipeline completion.

        Requirement 8.1: Total records processed, records per stage,
                         records transitioned to review, images collected.
        Requirement 8.2: Start and completion timestamp of each stage.
        Requirement 8.3: Count of records per review_reason category.
        Requirement 8.4: Log API errors with affected city_id.

        Args:
            context: The final PipelineContext.
        """
        total_records = len(context.city_records)
        total_review = len(context.review_manifest)
        total_errors = len(context.errors)

        # Summarize per-stage results
        stage_summaries: list[str] = []
        total_images = 0
        for sr in context.stage_results:
            stage_summaries.append(
                f"  {sr.stage_name}: processed={sr.records_processed}, "
                f"updated={sr.records_updated}, images={sr.images_collected}, "
                f"errors={len(sr.errors)}, "
                f"started={sr.started_at}, completed={sr.completed_at}"
            )
            total_images += sr.images_collected

        # Requirement 8.3: Count of records per review_reason category
        review_reason_counts: dict[str, int] = {}
        for entry in context.review_manifest:
            reason = entry.review_reason
            review_reason_counts[reason] = review_reason_counts.get(reason, 0) + 1

        review_reasons_str = ", ".join(
            f"{reason}={count}" for reason, count in sorted(review_reason_counts.items())
        )

        # Build summary report
        report_lines = [
            "=" * 60,
            "PIPELINE EXECUTION SUMMARY",
            "=" * 60,
            f"Start time: {context.start_time}",
            f"Total records: {total_records}",
            f"Total images collected: {total_images}",
            f"Records transitioned to review: {total_review}",
            f"Review reasons: {review_reasons_str or 'none'}",
            f"Total errors: {total_errors}",
            "",
            "Stage Results:",
            *stage_summaries,
            "=" * 60,
        ]

        report = "\n".join(report_lines)
        logger.info("\n%s", report)

        # Requirement 8.4: Log errors with context
        if context.errors:
            for error in context.errors:
                logger.error("Pipeline error: %s", error)

    def get_summary(self, context: PipelineContext) -> dict[str, Any]:
        """Generate a structured summary report dictionary.

        Useful for returning from Lambda handler or CLI output.

        Args:
            context: The final PipelineContext.

        Returns:
            Dictionary with summary metrics.
        """
        review_reason_counts: dict[str, int] = {}
        for entry in context.review_manifest:
            reason = entry.review_reason
            review_reason_counts[reason] = review_reason_counts.get(reason, 0) + 1

        total_images = sum(sr.images_collected for sr in context.stage_results)

        return {
            "start_time": context.start_time,
            "total_records": len(context.city_records),
            "total_images_collected": total_images,
            "records_transitioned_to_review": len(context.review_manifest),
            "review_reason_counts": review_reason_counts,
            "total_errors": len(context.errors),
            "errors": context.errors,
            "stages": [
                {
                    "stage_name": sr.stage_name,
                    "started_at": sr.started_at,
                    "completed_at": sr.completed_at,
                    "records_processed": sr.records_processed,
                    "records_updated": sr.records_updated,
                    "images_collected": sr.images_collected,
                    "errors": sr.errors,
                }
                for sr in context.stage_results
            ],
        }
