from __future__ import annotations

from dataclasses import dataclass
from typing import Final, TypedDict


PROTECTED_RESOURCE_TYPES: Final = frozenset(
    {
        "aws_dynamodb_table",
        "aws_s3_bucket",
        "aws_s3_bucket_object",
        "aws_s3_object",
    }
)
PROTECTED_RESOURCE_ADDRESSES: Final = frozenset({"terraform_data.kr_vector_index"})
BLOCKED_ACTIONS: Final = frozenset({"delete"})


class TerraformResourceChangeActions(TypedDict):
    actions: list[str]


class TerraformResourceChange(TypedDict):
    address: str
    change: TerraformResourceChangeActions


class TerraformPlan(TypedDict):
    resource_changes: list[TerraformResourceChange]


@dataclass(frozen=True, slots=True)
class TerraformPlanGuardReport:
    passed: bool
    failures: tuple[str, ...]
    action_summary: dict[str, tuple[str, ...]]


def evaluate_terraform_plan(plan: TerraformPlan) -> TerraformPlanGuardReport:
    action_summary = {
        change["address"]: tuple(change["change"]["actions"])
        for change in plan["resource_changes"]
    }
    failures = tuple(
        _protected_failure(address, actions)
        for address, actions in action_summary.items()
        if _is_protected(address) and _has_blocked_action(actions)
    )
    return TerraformPlanGuardReport(
        passed=len(failures) == 0,
        failures=failures,
        action_summary=action_summary,
    )


def protected_action_summary(
    report: TerraformPlanGuardReport,
) -> dict[str, tuple[str, ...]]:
    return {
        address: actions
        for address, actions in report.action_summary.items()
        if _is_protected(address)
    }


def _protected_failure(address: str, actions: tuple[str, ...]) -> str:
    return f"Protected resource {address} has {'/'.join(actions)}"


def _is_protected(address: str) -> bool:
    resource_type = address.partition(".")[0]
    return (
        resource_type in PROTECTED_RESOURCE_TYPES
        or address in PROTECTED_RESOURCE_ADDRESSES
    )


def _has_blocked_action(actions: tuple[str, ...]) -> bool:
    return any(action in BLOCKED_ACTIONS for action in actions)
