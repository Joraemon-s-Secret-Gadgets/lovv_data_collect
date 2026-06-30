from kr_vector_index.terraform_plan_guard import (
    TerraformPlan,
    TerraformResourceChange,
    evaluate_terraform_plan,
)


def test_evaluate_terraform_plan_passes_when_protected_resources_are_no_op() -> None:
    # Given: a Terraform plan updates only execution-plane resources.
    plan: TerraformPlan = {
        "resource_changes": [
            _change("aws_dynamodb_table.tourkorea_domain_data", ["no-op"]),
            _change("aws_dynamodb_table.tourkorea_domain_data_v2", ["no-op"]),
            _change("aws_s3_bucket.pipeline", ["no-op"]),
            _change("aws_s3_bucket.pipeline_images", ["no-op"]),
            _change("terraform_data.kr_vector_index", ["no-op"]),
            _change("aws_lambda_function.kr_pipeline_vector", ["update"]),
            _change("aws_sfn_state_machine.kr_data_pipeline", ["update"]),
        ],
    }

    # When: the protected-resource guard evaluates the plan.
    report = evaluate_terraform_plan(plan)

    # Then: the plan is accepted and protected actions are still reported.
    assert report.passed is True
    assert report.failures == ()
    assert report.action_summary["aws_dynamodb_table.tourkorea_domain_data"] == (
        "no-op",
    )
    assert report.action_summary["aws_sfn_state_machine.kr_data_pipeline"] == (
        "update",
    )


def test_evaluate_terraform_plan_blocks_protected_deletes_and_recreates() -> None:
    # Given: a Terraform plan attempts to delete or replace protected data-plane resources.
    plan: TerraformPlan = {
        "resource_changes": [
            _change("aws_dynamodb_table.tourkorea_domain_data_v2", ["delete", "create"]),
            _change("aws_s3_bucket.pipeline", ["delete"]),
            _change("aws_s3_object.raw_details", ["delete"]),
            _change("terraform_data.kr_vector_index", ["delete", "create"]),
            _change("aws_lambda_function.kr_pipeline_vector", ["update"]),
        ],
    }

    # When: the protected-resource guard evaluates the plan.
    report = evaluate_terraform_plan(plan)

    # Then: every protected delete or recreate is named as an apply blocker.
    assert report.passed is False
    assert (
        "Protected resource aws_dynamodb_table.tourkorea_domain_data_v2 has delete/create"
        in report.failures
    )
    assert "Protected resource aws_s3_bucket.pipeline has delete" in report.failures
    assert "Protected resource aws_s3_object.raw_details has delete" in report.failures
    assert "Protected resource terraform_data.kr_vector_index has delete/create" in report.failures


def _change(address: str, actions: list[str]) -> TerraformResourceChange:
    return {
        "address": address,
        "change": {"actions": actions},
    }
