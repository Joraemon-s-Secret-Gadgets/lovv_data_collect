from kr_vector_index.live_verification import (
    LiveVerificationSnapshot,
    verify_live_snapshot,
)


def test_verify_live_snapshot_passes_when_apply_wiring_is_present():
    # Given: live AWS responses match the post-apply execution-plane contract.
    snapshot = _matching_snapshot()

    # When: the read-only live verifier evaluates the snapshot.
    report = verify_live_snapshot(snapshot)

    # Then: all required post-apply gates pass.
    assert report.passed is True
    assert report.failures == ()


def test_verify_live_snapshot_flags_old_loader_route_and_delete_permissions():
    # Given: live AWS still has the pre-apply vector route and delete permissions.
    snapshot = _drifted_snapshot()

    # When: the read-only live verifier evaluates the snapshot.
    report = verify_live_snapshot(snapshot)

    # Then: the exact apply-blocking drift is reported.
    assert report.passed is False
    assert "Step Functions still routes vector-build to kr-pipeline-loader" in report.failures
    assert "Lambda IAM policy still allows dynamodb:DeleteItem" in report.failures
    assert "Lambda IAM policy still allows s3:DeleteObject" in report.failures
    assert "visitor_statistics live row count is not 2,820" not in report.failures
    assert "visitor_statistics coverage is not OK" not in report.failures
    assert report.observations == (
        "visitor_statistics rows=2820",
        "visitor_statistics coverage_ok=True",
        "enrichment mode=non-enrichment-complete",
    )


def _matching_snapshot() -> LiveVerificationSnapshot:
    return LiveVerificationSnapshot(
        loader_config={
            "Description": "KR pipeline loader Lambda for S3-to-DynamoDB load",
            "Environment": {"Variables": {"DYNAMODB_TABLE": "TourKoreaDomainDataV2"}},
        },
        vector_config={
            "Environment": {
                "Variables": {
                    "VECTOR_BUCKET": "lovv-vector-dev",
                    "VECTOR_INDEX": "kr-tour-domain-v2",
                    "MANIFEST_BUCKET": "lovv-data-pipeline-dev-925273580929",
                    "MANIFEST_PREFIX": "processed/KR/vector/manifests",
                },
            },
        },
        iam_policy={
            "Statement": [
                {"Action": ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"]},
                {"Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject"]},
            ],
        },
        state_machine={
            "States": {
                "LoadStage": {
                    "Type": "Task",
                    "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-loader",
                    "Parameters": {"command": "load"},
                    "Next": "VisitorStatsCoverageGate",
                },
                "VisitorStatsCoverageGate": {
                    "Type": "Task",
                    "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-vector",
                    "Parameters": {"command": "preflight"},
                    "Next": "VisitorStatsCoverageChoice",
                },
                "EnrichmentFieldLoadingGate": {"Type": "Choice"},
                "VectorPlanStage": {
                    "Type": "Task",
                    "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-vector",
                    "Parameters": {"command": "plan"},
                    "Next": "VectorBatchStage",
                },
                "VectorBatchStage": {
                    "Type": "Map",
                    "MaxConcurrency": 5,
                    "Next": "VectorAggregateStage",
                    "Iterator": {
                        "States": {
                            "InvokeVectorWorker": {
                                "Type": "Task",
                                "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-vector",
                                "Parameters": {"command": "worker"},
                            },
                        },
                    },
                },
                "VectorAggregateStage": {
                    "Type": "Task",
                    "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-vector",
                    "Parameters": {"command": "aggregate"},
                },
            },
        },
        preflight_summary={
            "visitor_statistics": {
                "expected_rows": 2820,
                "row_count": 2820,
                "coverage_ok": True,
            },
            "enrichment": {"mode": "non-enrichment-complete"},
        },
    )


def _drifted_snapshot() -> LiveVerificationSnapshot:
    matching = _matching_snapshot()
    return LiveVerificationSnapshot(
        loader_config={
            "Description": "KR pipeline loader Lambda for S3-to-DynamoDB load and vector index rebuild",
            "Environment": {
                "Variables": {
                    "DYNAMODB_TABLE": "TourKoreaDomainDataV2",
                    "VECTOR_BUCKET": "lovv-vector-dev",
                    "VECTOR_INDEX": "kr-tour-domain-v2",
                },
            },
        },
        vector_config=matching.vector_config,
        iam_policy={
            "Statement": [
                {"Action": ["dynamodb:PutItem", "dynamodb:DeleteItem"]},
                {"Action": ["s3:GetObject", "s3:DeleteObject"]},
            ],
        },
        state_machine={
            "States": {
                "VectorStage": {
                    "Type": "Task",
                    "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-loader",
                    "Parameters": {"command": "vector-build"},
                },
            },
        },
        preflight_summary=matching.preflight_summary,
    )
