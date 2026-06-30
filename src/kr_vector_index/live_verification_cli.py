from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Callable, Final, Sequence

from kr_vector_index.live_verification import (
    EnrichmentSummary,
    IamPolicyDocument,
    LambdaConfiguration,
    LiveVerificationSnapshot,
    PreflightSummary,
    StateMachineDefinition,
    VerificationReport,
    VisitorStatisticsSummary,
    verify_live_snapshot,
)
from kr_vector_index.preflight import build_preflight_summary


DEFAULT_REGION: Final = "us-east-1"
DEFAULT_TABLE_NAME: Final = "TourKoreaDomainDataV2"
DEFAULT_ENTITY_INDEX_NAME: Final = "EntityTypeDomainIndex"
DEFAULT_LOADER_FUNCTION: Final = "kr-pipeline-loader"
DEFAULT_VECTOR_FUNCTION: Final = "kr-pipeline-vector"
DEFAULT_ROLE_NAME: Final = "lovv-data-pipeline-lambda-dev"
DEFAULT_POLICY_NAME: Final = "lovv-data-pipeline-lambda-policy-dev"
DEFAULT_STATE_MACHINE_ARN: Final = (
    "arn:aws:states:us-east-1:925273580929:stateMachine:kr-data-pipeline-dev"
)

PreflightBuilder = Callable[..., dict[str, Any]]


@dataclass(frozen=True, slots=True)
class LiveVerifierConfig:
    region: str = DEFAULT_REGION
    profile: str | None = None
    table_name: str = DEFAULT_TABLE_NAME
    entity_index_name: str = DEFAULT_ENTITY_INDEX_NAME
    loader_function_name: str = DEFAULT_LOADER_FUNCTION
    vector_function_name: str = DEFAULT_VECTOR_FUNCTION
    role_name: str = DEFAULT_ROLE_NAME
    policy_name: str = DEFAULT_POLICY_NAME
    state_machine_arn: str = DEFAULT_STATE_MACHINE_ARN


def parse_args(argv: Sequence[str] | None = None) -> LiveVerifierConfig:
    parser = argparse.ArgumentParser(
        description="Verify KR Lambda/SFN post-apply wiring with read-only AWS calls."
    )
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--table-name", default=DEFAULT_TABLE_NAME)
    parser.add_argument("--entity-index-name", default=DEFAULT_ENTITY_INDEX_NAME)
    parser.add_argument("--loader-function-name", default=DEFAULT_LOADER_FUNCTION)
    parser.add_argument("--vector-function-name", default=DEFAULT_VECTOR_FUNCTION)
    parser.add_argument("--role-name", default=DEFAULT_ROLE_NAME)
    parser.add_argument("--policy-name", default=DEFAULT_POLICY_NAME)
    parser.add_argument("--state-machine-arn", default=DEFAULT_STATE_MACHINE_ARN)
    args = parser.parse_args(argv)
    return LiveVerifierConfig(
        region=args.region,
        profile=args.profile,
        table_name=args.table_name,
        entity_index_name=args.entity_index_name,
        loader_function_name=args.loader_function_name,
        vector_function_name=args.vector_function_name,
        role_name=args.role_name,
        policy_name=args.policy_name,
        state_machine_arn=args.state_machine_arn,
    )


def build_live_snapshot(
    session: Any,
    config: LiveVerifierConfig,
    *,
    preflight_builder: PreflightBuilder = build_preflight_summary,
) -> LiveVerificationSnapshot:
    lambda_client = session.client("lambda")
    iam_client = session.client("iam")
    sfn_client = session.client("stepfunctions")
    ddb_client = session.client("dynamodb")
    state_machine_response = sfn_client.describe_state_machine(
        stateMachineArn=config.state_machine_arn
    )
    preflight = preflight_builder(
        ddb_client,
        table_name=config.table_name,
        entity_index_name=config.entity_index_name,
    )
    return LiveVerificationSnapshot(
        loader_config=_lambda_config(
            lambda_client.get_function_configuration(
                FunctionName=config.loader_function_name
            )
        ),
        vector_config=_lambda_config(
            lambda_client.get_function_configuration(
                FunctionName=config.vector_function_name
            )
        ),
        iam_policy=_iam_policy(
            iam_client.get_role_policy(
                RoleName=config.role_name,
                PolicyName=config.policy_name,
            )["PolicyDocument"]
        ),
        state_machine=_state_machine(
            json.loads(str(state_machine_response["definition"]))
        ),
        preflight_summary=_preflight_summary(preflight),
    )


def run_verification(
    session: Any,
    config: LiveVerifierConfig,
    *,
    preflight_builder: PreflightBuilder = build_preflight_summary,
) -> int:
    snapshot = build_live_snapshot(
        session,
        config,
        preflight_builder=preflight_builder,
    )
    report = verify_live_snapshot(snapshot)
    print(json.dumps(_report_payload(report), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    import boto3

    session_kwargs: dict[str, str] = {"region_name": config.region}
    if config.profile:
        session_kwargs["profile_name"] = config.profile
    session = boto3.Session(**session_kwargs)
    return run_verification(session, config)


def _report_payload(report: VerificationReport) -> dict[str, Any]:
    observations = {
        item.partition("=")[0].replace(" ", "_"): _parse_observation_value(
            item.partition("=")[2]
        )
        for item in report.observations
    }
    return {
        "passed": report.passed,
        "failures": list(report.failures),
        "observations": observations,
    }


def _parse_observation_value(value: str) -> str | int | bool:
    match value:
        case "True":
            return True
        case "False":
            return False
        case _ if value.isdecimal():
            return int(value)
        case _:
            return value


def _lambda_config(value: LambdaConfiguration) -> LambdaConfiguration:
    return value


def _iam_policy(value: IamPolicyDocument) -> IamPolicyDocument:
    return value


def _state_machine(value: StateMachineDefinition) -> StateMachineDefinition:
    return value


def _preflight_summary(value: dict[str, Any]) -> PreflightSummary:
    visitor = value["visitor_statistics"]
    enrichment = value["enrichment"]
    return {
        "visitor_statistics": VisitorStatisticsSummary(
            expected_rows=int(visitor["expected_rows"]),
            row_count=int(visitor["row_count"]),
            coverage_ok=bool(visitor["coverage_ok"]),
        ),
        "enrichment": EnrichmentSummary(mode=str(enrichment["mode"])),
    }


if __name__ == "__main__":
    raise SystemExit(main())
