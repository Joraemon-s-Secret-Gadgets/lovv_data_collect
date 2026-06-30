import json

from kr_vector_index.live_verification_cli import (
    LiveVerifierConfig,
    build_live_snapshot,
    run_verification,
)


def test_build_live_snapshot_reads_all_apply_verification_sources():
    # Given: fake AWS clients expose post-apply Lambda, IAM, SFN, and preflight data.
    session = _matching_session()
    config = LiveVerifierConfig()

    # When: the CLI snapshot collector reads the configured live resources.
    snapshot = build_live_snapshot(
        session,
        config,
        preflight_builder=_matching_preflight,
    )

    # Then: the snapshot can be evaluated by the shared verifier contract.
    assert snapshot.loader_config["Description"] == "KR pipeline loader Lambda for S3-to-DynamoDB load"
    assert snapshot.preflight_summary["visitor_statistics"]["row_count"] == 2820
    assert snapshot.preflight_summary["enrichment"]["mode"] == "non-enrichment-complete"


def test_run_verification_prints_json_and_returns_failure_for_pre_apply_drift(capsys):
    # Given: fake AWS clients still expose the pre-apply loader vector route.
    session = _drifted_session()
    config = LiveVerifierConfig()

    # When: the CLI verifier evaluates the snapshot.
    exit_code = run_verification(
        session,
        config,
        preflight_builder=_matching_preflight,
    )

    # Then: operators receive machine-readable failure output.
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["passed"] is False
    assert "Step Functions still routes vector-build to kr-pipeline-loader" in payload["failures"]
    assert payload["observations"]["visitor_statistics_rows"] == 2820


class FakeSession:
    def __init__(self, state_machine_definition: dict):
        self.state_machine_definition = state_machine_definition

    def client(self, service_name: str):
        clients = {
            "lambda": FakeLambdaClient(),
            "iam": FakeIamClient(),
            "stepfunctions": FakeStepFunctionsClient(self.state_machine_definition),
            "dynamodb": FakeDynamoDbClient(),
        }
        return clients[service_name]


class FakeLambdaClient:
    def get_function_configuration(self, *, FunctionName: str) -> dict:
        configs = {
            "kr-pipeline-loader": {
                "Description": "KR pipeline loader Lambda for S3-to-DynamoDB load",
                "Environment": {"Variables": {"DYNAMODB_TABLE": "TourKoreaDomainDataV2"}},
            },
            "kr-pipeline-vector": {
                "Environment": {
                    "Variables": {
                        "VECTOR_BUCKET": "lovv-vector-dev",
                        "VECTOR_INDEX": "kr-tour-domain-v2",
                        "MANIFEST_BUCKET": "lovv-data-pipeline-dev-925273580929",
                        "MANIFEST_PREFIX": "processed/KR/vector/manifests",
                    },
                },
            },
        }
        return configs[FunctionName]


class FakeIamClient:
    def get_role_policy(self, *, RoleName: str, PolicyName: str) -> dict:
        return {
            "RoleName": RoleName,
            "PolicyName": PolicyName,
            "PolicyDocument": {
                "Statement": [{"Action": ["dynamodb:GetItem", "s3:GetObject"]}],
            },
        }


class FakeStepFunctionsClient:
    def __init__(self, definition: dict):
        self.definition = definition

    def describe_state_machine(self, *, stateMachineArn: str) -> dict:
        return {"stateMachineArn": stateMachineArn, "definition": json.dumps(self.definition)}


class FakeDynamoDbClient:
    pass


def _matching_preflight(
    dynamodb_client: FakeDynamoDbClient,
    *,
    table_name: str,
    entity_index_name: str,
) -> dict:
    return {
        "table_name": table_name,
        "entity_index_name": entity_index_name,
        "visitor_statistics": {
            "expected_rows": 2820,
            "row_count": 2820,
            "coverage_ok": True,
        },
        "enrichment": {"mode": "non-enrichment-complete"},
    }


def _matching_session() -> FakeSession:
    return FakeSession(_matching_state_machine())


def _drifted_session() -> FakeSession:
    return FakeSession(
        {
            "States": {
                "VectorStage": {
                    "Type": "Task",
                    "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-loader",
                    "Parameters": {"command": "vector-build"},
                },
            },
        }
    )


def _matching_state_machine() -> dict:
    return {
        "States": {
            "VisitorStatsCoverageGate": {
                "Type": "Task",
                "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-vector",
                "Parameters": {"command": "preflight"},
            },
            "EnrichmentFieldLoadingGate": {"Type": "Choice"},
            "VectorPlanStage": {
                "Type": "Task",
                "Resource": "arn:aws:lambda:us-east-1:123:function:kr-pipeline-vector",
                "Parameters": {"command": "plan"},
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
        }
    }
