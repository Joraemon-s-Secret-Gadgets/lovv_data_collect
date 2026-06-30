import json
from io import StringIO
from pathlib import Path

from kr_vector_index.terraform_plan_guard_cli import (
    PlanGuardCliConfig,
    PlanGuardCliContext,
    run_plan_guard,
)
from kr_vector_index.terraform_plan_guard import TerraformPlan, TerraformResourceChange


def test_run_plan_guard_reads_stdin_and_prints_success_payload() -> None:
    # Given: Terraform plan JSON is piped into stdin.
    stdout = StringIO()
    context = PlanGuardCliContext(
        config=PlanGuardCliConfig(),
        stdin=StringIO(json.dumps(_safe_plan())),
        stdout=stdout,
    )

    # When: the CLI guard evaluates stdin.
    exit_code = run_plan_guard(context)

    # Then: the process result is successful and machine-readable.
    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["failures"] == []
    assert payload["protected"]["aws_s3_bucket.pipeline"] == ["no-op"]


def test_run_plan_guard_reads_file_and_blocks_protected_delete(tmp_path: Path) -> None:
    # Given: Terraform plan JSON is saved to a file and includes an S3 bucket delete.
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_unsafe_plan()), encoding="utf-8")
    stdout = StringIO()
    context = PlanGuardCliContext(
        config=PlanGuardCliConfig(plan_json_path=plan_path),
        stdin=StringIO(""),
        stdout=stdout,
    )

    # When: the CLI guard evaluates the saved plan JSON.
    exit_code = run_plan_guard(context)

    # Then: the process result blocks apply and names the protected resource.
    payload = json.loads(stdout.getvalue())
    assert exit_code == 1
    assert payload["passed"] is False
    assert "Protected resource aws_s3_bucket.pipeline has delete" in payload["failures"]


def _safe_plan() -> TerraformPlan:
    return {
        "resource_changes": [
            _change("aws_dynamodb_table.tourkorea_domain_data", ["no-op"]),
            _change("aws_s3_bucket.pipeline", ["no-op"]),
            _change("terraform_data.kr_vector_index", ["no-op"]),
            _change("aws_sfn_state_machine.kr_data_pipeline", ["update"]),
        ],
    }


def _unsafe_plan() -> TerraformPlan:
    return {
        "resource_changes": [
            _change("aws_s3_bucket.pipeline", ["delete"]),
            _change("aws_lambda_function.kr_pipeline_vector", ["update"]),
        ],
    }


def _change(address: str, actions: list[str]) -> TerraformResourceChange:
    return {
        "address": address,
        "change": {"actions": actions},
    }
