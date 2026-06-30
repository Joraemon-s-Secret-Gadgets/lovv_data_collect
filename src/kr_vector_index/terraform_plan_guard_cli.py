from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, TextIO, TypedDict

from kr_vector_index.terraform_plan_guard import (
    TerraformPlan,
    TerraformPlanGuardReport,
    evaluate_terraform_plan,
    protected_action_summary,
)


class PlanGuardPayload(TypedDict):
    passed: bool
    failures: list[str]
    protected: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class PlanGuardCliConfig:
    plan_json_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PlanGuardCliContext:
    config: PlanGuardCliConfig
    stdin: TextIO
    stdout: TextIO


def parse_args(argv: Sequence[str] | None = None) -> PlanGuardCliConfig:
    parser = argparse.ArgumentParser(
        description="Verify Terraform plan JSON does not delete protected data-plane resources."
    )
    parser.add_argument(
        "--plan-json",
        type=Path,
        default=None,
        help="Path to terraform show -json output. Reads stdin when omitted.",
    )
    args = parser.parse_args(argv)
    return PlanGuardCliConfig(plan_json_path=args.plan_json)


def run_plan_guard(context: PlanGuardCliContext) -> int:
    plan = _read_plan(context)
    report = evaluate_terraform_plan(plan)
    print(json.dumps(_report_payload(report), ensure_ascii=False, indent=2), file=context.stdout)
    return 0 if report.passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_plan_guard(
        PlanGuardCliContext(
            config=parse_args(argv),
            stdin=sys.stdin,
            stdout=sys.stdout,
        )
    )


def _read_plan(context: PlanGuardCliContext) -> TerraformPlan:
    path = context.config.plan_json_path
    if path is None:
        return json.loads(context.stdin.read())
    return json.loads(path.read_text(encoding="utf-8"))


def _report_payload(report: TerraformPlanGuardReport) -> PlanGuardPayload:
    return {
        "passed": report.passed,
        "failures": list(report.failures),
        "protected": {
            address: list(actions)
            for address, actions in protected_action_summary(report).items()
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
