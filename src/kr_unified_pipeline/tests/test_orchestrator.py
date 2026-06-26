"""Unit tests for the UnifiedPipeline orchestrator."""

from __future__ import annotations

import pytest

from kr_unified_pipeline.completeness import CompletenessEvaluator
from kr_unified_pipeline.models import (
    CityRecord,
    PipelineConfig,
    PipelineContext,
    StageResult,
)
from kr_unified_pipeline.orchestrator import UnifiedPipeline
from kr_unified_pipeline.review_transition import ReviewTransition
from kr_unified_pipeline.stages import PipelineStage, STAGE_ORDER


# ---------------------------------------------------------------------------
# Helpers: Fake stage implementations for testing
# ---------------------------------------------------------------------------


class FakeStage:
    """A fake PipelineStage that records calls and optionally adds records."""

    def __init__(self, name: str, records_to_add: list[CityRecord] | None = None, should_fail: bool = False):
        self._name = name
        self._records_to_add = records_to_add or []
        self._should_fail = should_fail
        self.executed = False
        self.execution_order: int | None = None

    @property
    def name(self) -> str:
        return self._name

    def execute(self, context: PipelineContext) -> PipelineContext:
        if self._should_fail:
            raise RuntimeError(f"Stage '{self._name}' encountered a fatal error")
        self.executed = True
        for record in self._records_to_add:
            if not any(r.city_id == record.city_id for r in context.city_records):
                context.city_records.append(record)
        return context


# Execution order tracker
_execution_counter = 0


class OrderedFakeStage(FakeStage):
    """Tracks execution order across multiple stages."""

    def execute(self, context: PipelineContext) -> PipelineContext:
        global _execution_counter
        _execution_counter += 1
        self.execution_order = _execution_counter
        return super().execute(context)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def complete_record() -> CityRecord:
    return CityRecord(
        city_id="city-001",
        city_name_ko="서울특별시",
        prefecture_id="KR-11",
        latitude=37.5665,
        longitude=126.9780,
        description="대한민국의 수도",
        image_url="https://example.com/seoul.jpg",
    )


@pytest.fixture
def incomplete_record() -> CityRecord:
    return CityRecord(
        city_id="city-002",
        city_name_ko="부산광역시",
        prefecture_id="KR-26",
        latitude=None,
        longitude=None,
        description="",
    )


@pytest.fixture
def basic_config() -> PipelineConfig:
    return PipelineConfig(skip_images=True)


# ---------------------------------------------------------------------------
# Tests: Stage resolution and canonical order
# ---------------------------------------------------------------------------


class TestStageResolution:
    """Tests for stage ordering and selection logic."""

    def test_all_stages_by_default(self, basic_config: PipelineConfig):
        """When no stages specified, all stages in canonical order are used."""
        pipeline = UnifiedPipeline(config=basic_config)
        resolved = pipeline._resolve_stages()
        assert resolved == list(STAGE_ORDER)

    def test_specific_stages_filtered(self):
        """When stages are specified, only those stages run in canonical order."""
        config = PipelineConfig(stages=["tourapi-detail", "wikipedia"], skip_images=True)
        pipeline = UnifiedPipeline(config=config)
        resolved = pipeline._resolve_stages()
        # Should be in canonical order: wikipedia before tourapi-detail
        assert resolved == ["wikipedia", "tourapi-detail"]

    def test_single_stage(self):
        """Single stage specification works."""
        config = PipelineConfig(stages=["tourapi-region"], skip_images=True)
        pipeline = UnifiedPipeline(config=config)
        resolved = pipeline._resolve_stages()
        assert resolved == ["tourapi-region"]

    def test_unknown_stages_ignored(self):
        """Stages not in STAGE_ORDER are silently excluded."""
        config = PipelineConfig(stages=["unknown-stage", "wikipedia"], skip_images=True)
        pipeline = UnifiedPipeline(config=config)
        resolved = pipeline._resolve_stages()
        assert resolved == ["wikipedia"]


# ---------------------------------------------------------------------------
# Tests: Pipeline execution
# ---------------------------------------------------------------------------


class TestPipelineExecution:
    """Tests for the main run() method."""

    def test_run_creates_context_when_none(self, basic_config: PipelineConfig):
        """run() creates a PipelineContext if not provided."""
        pipeline = UnifiedPipeline(config=basic_config)
        ctx = pipeline.run()
        assert ctx is not None
        assert ctx.start_time != ""
        assert ctx.config is basic_config

    def test_run_uses_provided_context(self, basic_config: PipelineConfig, complete_record: CityRecord):
        """run() uses an existing context when provided."""
        pipeline = UnifiedPipeline(config=basic_config)
        existing_ctx = PipelineContext(
            config=basic_config,
            start_time="2024-01-01T00:00:00+00:00",
            city_records=[complete_record],
        )
        ctx = pipeline.run(context=existing_ctx)
        assert ctx is existing_ctx
        assert ctx.start_time == "2024-01-01T00:00:00+00:00"

    def test_stages_execute_in_canonical_order(self):
        """Stages execute in STAGE_ORDER regardless of registration order."""
        global _execution_counter
        _execution_counter = 0

        config = PipelineConfig(
            stages=["tourapi-detail", "wikipedia", "tourapi-region"],
            skip_images=True,
        )
        wiki_stage = OrderedFakeStage("wikipedia")
        region_stage = OrderedFakeStage("tourapi-region")
        detail_stage = OrderedFakeStage("tourapi-detail")

        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": wiki_stage,
            "tourapi-region": region_stage,
            "tourapi-detail": detail_stage,
        })

        pipeline.run()

        assert wiki_stage.execution_order == 1
        assert region_stage.execution_order == 2
        assert detail_stage.execution_order == 3

    def test_context_passed_between_stages(self, basic_config: PipelineConfig):
        """Context accumulates records from each stage."""
        record_a = CityRecord(city_id="a", city_name_ko="도시A", prefecture_id="KR-01",
                              latitude=35.0, longitude=127.0, description="설명A")
        record_b = CityRecord(city_id="b", city_name_ko="도시B", prefecture_id="KR-02",
                              latitude=36.0, longitude=128.0, description="설명B")

        config = PipelineConfig(stages=["wikipedia", "tourapi-region"], skip_images=True)
        wiki_stage = FakeStage("wikipedia", records_to_add=[record_a])
        region_stage = FakeStage("tourapi-region", records_to_add=[record_b])

        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": wiki_stage,
            "tourapi-region": region_stage,
        })

        ctx = pipeline.run()
        assert len(ctx.city_records) == 2
        city_ids = {r.city_id for r in ctx.city_records}
        assert city_ids == {"a", "b"}

    def test_stage_results_accumulated(self, basic_config: PipelineConfig):
        """Each executed stage produces a StageResult in context."""
        config = PipelineConfig(stages=["wikipedia", "tourapi-region"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia"),
            "tourapi-region": FakeStage("tourapi-region"),
        })

        ctx = pipeline.run()
        assert len(ctx.stage_results) == 2
        assert ctx.stage_results[0].stage_name == "wikipedia"
        assert ctx.stage_results[1].stage_name == "tourapi-region"
        # Both should have timestamps
        assert ctx.stage_results[0].started_at != ""
        assert ctx.stage_results[0].completed_at != ""

    def test_missing_stage_implementation_skipped(self):
        """Stages without registered implementations are skipped."""
        config = PipelineConfig(stages=["wikipedia", "tourapi-region"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia"),
            # tourapi-region not registered
        })

        ctx = pipeline.run()
        # Only wikipedia stage result should appear
        assert len(ctx.stage_results) == 1
        assert ctx.stage_results[0].stage_name == "wikipedia"


# ---------------------------------------------------------------------------
# Tests: Stage failure handling
# ---------------------------------------------------------------------------


class TestStageFailureHandling:
    """Tests for non-recoverable stage failure behavior."""

    def test_failed_stage_preserves_prior_results(self):
        """When a stage fails, results from prior stages are preserved."""
        record = CityRecord(city_id="prior", city_name_ko="이전", prefecture_id="KR-01",
                            latitude=35.0, longitude=127.0, description="이전 설명")

        config = PipelineConfig(
            stages=["wikipedia", "tourapi-region", "tourapi-detail"],
            skip_images=True,
        )
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia", records_to_add=[record]),
            "tourapi-region": FakeStage("tourapi-region", should_fail=True),
            "tourapi-detail": FakeStage("tourapi-detail"),
        })

        ctx = pipeline.run()

        # Prior records preserved
        assert len(ctx.city_records) == 1
        assert ctx.city_records[0].city_id == "prior"

        # Error recorded
        assert len(ctx.errors) == 1
        assert "tourapi-region" in ctx.errors[0]

        # Failed stage result recorded with error
        failed_result = next(sr for sr in ctx.stage_results if sr.stage_name == "tourapi-region")
        assert len(failed_result.errors) == 1

    def test_subsequent_stages_not_executed_after_failure(self):
        """Stages after a failed stage are not executed."""
        config = PipelineConfig(
            stages=["wikipedia", "tourapi-region", "tourapi-detail"],
            skip_images=True,
        )
        detail_stage = FakeStage("tourapi-detail")

        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia"),
            "tourapi-region": FakeStage("tourapi-region", should_fail=True),
            "tourapi-detail": detail_stage,
        })

        pipeline.run()
        assert detail_stage.executed is False

    def test_failed_stage_has_completed_at_timestamp(self):
        """Failed stage still gets a completed_at timestamp."""
        config = PipelineConfig(stages=["wikipedia"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia", should_fail=True),
        })

        ctx = pipeline.run()
        assert ctx.stage_results[0].completed_at != ""


# ---------------------------------------------------------------------------
# Tests: Post-stage processing (completeness + review transition)
# ---------------------------------------------------------------------------


class TestPostStageProcessing:
    """Tests for completeness evaluation and review transition after stages."""

    def test_completeness_evaluated_after_preprocessing_stage(self):
        """CompletenessEvaluator runs after each preprocessing stage."""
        # Missing city_name_ko → triggers "low" confidence
        incomplete = CityRecord(
            city_id="inc-001",
            city_name_ko="",
            prefecture_id="",
            latitude=None,
            longitude=None,
            description="",
        )

        config = PipelineConfig(stages=["wikipedia"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia", records_to_add=[incomplete]),
        })

        ctx = pipeline.run()

        # Record should have been evaluated and transitioned to "low"
        record = ctx.city_records[0]
        assert record.data_confidence == "low"

    def test_review_manifest_populated_for_incomplete_records(self):
        """Records needing review (low confidence) are added to the review manifest."""
        # Missing city_name_ko AND prefecture_id → "low" confidence → needs_review=True
        incomplete = CityRecord(
            city_id="inc-002",
            city_name_ko="",
            prefecture_id="",
            latitude=None,
            longitude=None,
            description="",
        )

        config = PipelineConfig(stages=["wikipedia"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia", records_to_add=[incomplete]),
        })

        ctx = pipeline.run()

        assert len(ctx.review_manifest) >= 1
        entry = ctx.review_manifest[0]
        assert entry.city_id == "inc-002"
        assert entry.review_reason in ("missing_coordinates", "empty_description", "low_confidence")

    def test_complete_records_not_in_review_manifest(self, complete_record: CityRecord):
        """Complete records are not added to the review manifest."""
        config = PipelineConfig(stages=["wikipedia"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia", records_to_add=[complete_record]),
        })

        ctx = pipeline.run()
        # Complete records should not be in review manifest
        review_ids = {e.city_id for e in ctx.review_manifest}
        assert complete_record.city_id not in review_ids

    def test_no_post_processing_for_non_preprocessing_stages(self):
        """Load and vector-build stages don't trigger completeness evaluation."""
        incomplete = CityRecord(
            city_id="load-001",
            city_name_ko="",
            prefecture_id="",
            latitude=None,
            longitude=None,
            description="",
        )

        config = PipelineConfig(stages=["load"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "load": FakeStage("load", records_to_add=[incomplete]),
        })

        ctx = pipeline.run()

        # No review manifest entries since load is not a preprocessing stage
        assert len(ctx.review_manifest) == 0


# ---------------------------------------------------------------------------
# Tests: Image resolution
# ---------------------------------------------------------------------------


class TestImageResolution:
    """Tests for image resolution during pipeline execution."""

    def test_image_resolver_not_created_when_skip_images(self):
        """When skip_images=True, no ImageResolver is created."""
        config = PipelineConfig(skip_images=True)
        pipeline = UnifiedPipeline(config=config)
        assert pipeline.image_resolver is None

    def test_image_resolver_created_when_images_enabled(self):
        """When skip_images=False, ImageResolver is created."""
        config = PipelineConfig(skip_images=False)
        pipeline = UnifiedPipeline(config=config)
        assert pipeline.image_resolver is not None

    def test_skip_images_prevents_image_resolution(self):
        """When skip_images=True, no image resolution occurs."""
        record = CityRecord(
            city_id="img-001",
            city_name_ko="서울",
            prefecture_id="KR-11",
            latitude=37.5,
            longitude=127.0,
            description="수도",
        )

        config = PipelineConfig(stages=["wikipedia"], skip_images=True)
        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia", records_to_add=[record]),
        })

        ctx = pipeline.run()
        # No images should be collected
        assert ctx.stage_results[0].images_collected == 0


# ---------------------------------------------------------------------------
# Tests: Summary report
# ---------------------------------------------------------------------------


class TestSummaryReport:
    """Tests for summary report generation."""

    def test_get_summary_returns_correct_structure(self, basic_config: PipelineConfig):
        """get_summary() returns a well-structured report dictionary."""
        config = PipelineConfig(stages=["wikipedia"], skip_images=True)
        record = CityRecord(
            city_id="sum-001",
            city_name_ko="도시",
            prefecture_id="KR-01",
            latitude=35.0,
            longitude=127.0,
            description="설명",
        )

        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": FakeStage("wikipedia", records_to_add=[record]),
        })

        ctx = pipeline.run()
        summary = pipeline.get_summary(ctx)

        assert "start_time" in summary
        assert summary["total_records"] == 1
        assert "total_images_collected" in summary
        assert "records_transitioned_to_review" in summary
        assert "review_reason_counts" in summary
        assert "total_errors" in summary
        assert "stages" in summary
        assert len(summary["stages"]) == 1
        assert summary["stages"][0]["stage_name"] == "wikipedia"

    def test_summary_counts_review_reasons(self):
        """Summary report correctly counts review reasons."""
        # Records must have "low" confidence to trigger needs_review=True
        # Low confidence requires missing city_name_ko or prefecture_id
        records = [
            CityRecord(city_id="r1", city_name_ko="", prefecture_id="",
                       latitude=None, longitude=None, description=""),
            CityRecord(city_id="r2", city_name_ko="", prefecture_id="KR-02",
                       latitude=None, longitude=None, description=""),
            CityRecord(city_id="r3", city_name_ko="", prefecture_id="",
                       latitude=35.0, longitude=127.0, description=""),
        ]

        config = PipelineConfig(stages=["wikipedia"], skip_images=True)

        class MultiRecordStage:
            @property
            def name(self) -> str:
                return "wikipedia"

            def execute(self, context: PipelineContext) -> PipelineContext:
                context.city_records.extend(records)
                return context

        pipeline = UnifiedPipeline(config=config, stages={
            "wikipedia": MultiRecordStage(),
        })

        ctx = pipeline.run()
        summary = pipeline.get_summary(ctx)

        # Should have review reason counts
        assert summary["records_transitioned_to_review"] > 0
        assert len(summary["review_reason_counts"]) > 0


# ---------------------------------------------------------------------------
# Tests: Register stage
# ---------------------------------------------------------------------------


class TestRegisterStage:
    """Tests for dynamic stage registration."""

    def test_register_stage_adds_to_mapping(self, basic_config: PipelineConfig):
        """register_stage() adds a stage by its name property."""
        pipeline = UnifiedPipeline(config=basic_config)
        stage = FakeStage("wikipedia")
        pipeline.register_stage(stage)
        assert "wikipedia" in pipeline.stages
        assert pipeline.stages["wikipedia"] is stage

    def test_register_stage_overrides_existing(self, basic_config: PipelineConfig):
        """Registering a stage with the same name replaces the previous one."""
        pipeline = UnifiedPipeline(config=basic_config)
        stage1 = FakeStage("wikipedia")
        stage2 = FakeStage("wikipedia")
        pipeline.register_stage(stage1)
        pipeline.register_stage(stage2)
        assert pipeline.stages["wikipedia"] is stage2
