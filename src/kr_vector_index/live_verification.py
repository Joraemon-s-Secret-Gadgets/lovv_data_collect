from __future__ import annotations

from dataclasses import dataclass
from typing import Final, NotRequired, TypedDict, assert_never


EXPECTED_VISITOR_STATISTICS_ROWS: Final = 2820
VALID_ENRICHMENT_MODES: Final = frozenset(
    {"enrichment-complete", "non-enrichment-complete"}
)
DELETE_ACTIONS: Final = frozenset({"dynamodb:DeleteItem", "s3:DeleteObject"})
LOADER_VECTOR_ENV_KEYS: Final = frozenset({"VECTOR_BUCKET", "VECTOR_INDEX"})


type IamAction = str | list[str]
type StateParameter = str | int | bool
type StateParameters = dict[str, StateParameter]


class LambdaEnvironment(TypedDict, total=False):
    Variables: dict[str, str]


class LambdaConfiguration(TypedDict, total=False):
    Description: str
    Environment: LambdaEnvironment


class IamStatement(TypedDict, total=False):
    Action: IamAction


class IamPolicyDocument(TypedDict):
    Statement: list[IamStatement]


class IteratorDefinition(TypedDict):
    States: dict[str, StateDefinition]


class StateDefinition(TypedDict, total=False):
    Type: str
    Resource: str
    Parameters: StateParameters
    Next: str
    MaxConcurrency: int
    Iterator: NotRequired[IteratorDefinition]


class StateMachineDefinition(TypedDict):
    States: dict[str, StateDefinition]


class VisitorStatisticsSummary(TypedDict):
    expected_rows: int
    row_count: int
    coverage_ok: bool


class EnrichmentSummary(TypedDict):
    mode: str


class PreflightSummary(TypedDict):
    visitor_statistics: VisitorStatisticsSummary
    enrichment: EnrichmentSummary


@dataclass(frozen=True, slots=True)
class LiveVerificationSnapshot:
    loader_config: LambdaConfiguration
    vector_config: LambdaConfiguration
    iam_policy: IamPolicyDocument
    state_machine: StateMachineDefinition
    preflight_summary: PreflightSummary


@dataclass(frozen=True, slots=True)
class VerificationReport:
    passed: bool
    failures: tuple[str, ...]
    observations: tuple[str, ...]


def verify_live_snapshot(snapshot: LiveVerificationSnapshot) -> VerificationReport:
    failures = (
        *_loader_failures(snapshot.loader_config),
        *_vector_lambda_failures(snapshot.vector_config),
        *_iam_failures(snapshot.iam_policy),
        *_state_machine_failures(snapshot.state_machine),
        *_preflight_failures(snapshot.preflight_summary),
    )
    observations = _preflight_observations(snapshot.preflight_summary)
    return VerificationReport(
        passed=len(failures) == 0,
        failures=failures,
        observations=observations,
    )


def _loader_failures(config: LambdaConfiguration) -> tuple[str, ...]:
    variables = config.get("Environment", {}).get("Variables", {})
    failures = [
        f"kr-pipeline-loader still carries {key}"
        for key in sorted(LOADER_VECTOR_ENV_KEYS)
        if key in variables
    ]
    description = config.get("Description", "")
    if "vector index rebuild" in description:
        failures.append("kr-pipeline-loader description still mentions vector rebuild")
    return tuple(failures)


def _vector_lambda_failures(config: LambdaConfiguration) -> tuple[str, ...]:
    variables = config.get("Environment", {}).get("Variables", {})
    required = ("VECTOR_BUCKET", "VECTOR_INDEX", "MANIFEST_BUCKET", "MANIFEST_PREFIX")
    return tuple(
        f"kr-pipeline-vector is missing {key}"
        for key in required
        if key not in variables
    )


def _iam_failures(policy: IamPolicyDocument) -> tuple[str, ...]:
    actions = set(_policy_actions(policy))
    return tuple(
        f"Lambda IAM policy still allows {action}"
        for action in sorted(DELETE_ACTIONS)
        if action in actions
    )


def _state_machine_failures(definition: StateMachineDefinition) -> tuple[str, ...]:
    failures = [
        *_required_stage_failures(definition),
        *_batch_stage_failures(definition),
    ]
    if _routes_loader_vector_build(definition):
        failures.append("Step Functions still routes vector-build to kr-pipeline-loader")
    return tuple(failures)


def _required_stage_failures(definition: StateMachineDefinition) -> tuple[str, ...]:
    expected_commands = {
        "VisitorStatsCoverageGate": "preflight",
        "VectorPlanStage": "plan",
        "VectorAggregateStage": "aggregate",
    }
    failures: list[str] = []
    states = definition["States"]
    if states.get("EnrichmentFieldLoadingGate", {}).get("Type") != "Choice":
        failures.append("Step Functions is missing EnrichmentFieldLoadingGate choice")
    for stage, command in expected_commands.items():
        state = states.get(stage)
        if state is None:
            failures.append(f"Step Functions is missing {stage}")
            continue
        if "kr-pipeline-vector" not in state.get("Resource", ""):
            failures.append(f"{stage} does not invoke kr-pipeline-vector")
        if _command(state) != command:
            failures.append(f"{stage} command is not {command}")
    return tuple(failures)


def _batch_stage_failures(definition: StateMachineDefinition) -> tuple[str, ...]:
    state = definition["States"].get("VectorBatchStage")
    if state is None:
        return ("Step Functions is missing VectorBatchStage",)
    failures: list[str] = []
    if state.get("Type") != "Map":
        failures.append("VectorBatchStage is not a Map state")
    if int(state.get("MaxConcurrency", 0)) < 1:
        failures.append("VectorBatchStage MaxConcurrency is not bounded")
    if state.get("Next") != "VectorAggregateStage":
        failures.append("VectorBatchStage does not flow to VectorAggregateStage")
    worker = state.get("Iterator", {}).get("States", {}).get("InvokeVectorWorker")
    if worker is None:
        failures.append("VectorBatchStage is missing InvokeVectorWorker")
        return tuple(failures)
    if "kr-pipeline-vector" not in worker.get("Resource", ""):
        failures.append("InvokeVectorWorker does not invoke kr-pipeline-vector")
    if _command(worker) != "worker":
        failures.append("InvokeVectorWorker command is not worker")
    return tuple(failures)


def _preflight_failures(summary: PreflightSummary) -> tuple[str, ...]:
    visitor = summary["visitor_statistics"]
    enrichment = summary["enrichment"]
    failures: list[str] = []
    if visitor["expected_rows"] != EXPECTED_VISITOR_STATISTICS_ROWS:
        failures.append("visitor_statistics expected row count changed")
    if visitor["row_count"] != EXPECTED_VISITOR_STATISTICS_ROWS:
        failures.append("visitor_statistics live row count is not 2,820")
    if not visitor["coverage_ok"]:
        failures.append("visitor_statistics coverage is not OK")
    if enrichment["mode"] not in VALID_ENRICHMENT_MODES:
        failures.append("enrichment mode is not recognized")
    return tuple(failures)


def _preflight_observations(summary: PreflightSummary) -> tuple[str, ...]:
    visitor = summary["visitor_statistics"]
    enrichment = summary["enrichment"]
    return (
        f"visitor_statistics rows={visitor['row_count']}",
        f"visitor_statistics coverage_ok={visitor['coverage_ok']}",
        f"enrichment mode={enrichment['mode']}",
    )


def _policy_actions(policy: IamPolicyDocument) -> tuple[str, ...]:
    actions: list[str] = []
    for statement in policy["Statement"]:
        actions.extend(_expand_action(statement.get("Action")))
    return tuple(actions)


def _expand_action(action: IamAction | None) -> tuple[str, ...]:
    match action:
        case str():
            return (action,)
        case list():
            return tuple(action)
        case None:
            return ()
        case unreachable:
            assert_never(unreachable)


def _routes_loader_vector_build(definition: StateMachineDefinition) -> bool:
    return any(
        "kr-pipeline-loader" in state.get("Resource", "")
        and _command(state) == "vector-build"
        for state in _iter_states(definition)
    )


def _iter_states(definition: StateMachineDefinition) -> tuple[StateDefinition, ...]:
    states: list[StateDefinition] = []
    for state in definition["States"].values():
        states.append(state)
        states.extend(state.get("Iterator", {}).get("States", {}).values())
    return tuple(states)


def _command(state: StateDefinition) -> str:
    return str(state.get("Parameters", {}).get("command") or "")
