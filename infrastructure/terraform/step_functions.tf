# -----------------------------------------------------------------------------
# Step Functions 상태 머신 — KR Data Pipeline E2E 오케스트레이션
# -----------------------------------------------------------------------------
# 211개 도시 관광 데이터를 순차적으로 Transform → Image → Load → Vector 처리하며,
# Map State를 사용해 도시 단위 병렬 처리로 Lambda 15분 타임아웃 제약을 해결합니다.

# -----------------------------------------------------------------------------
# CloudWatch Log Group for Step Functions execution logging
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "sfn_logs" {
  name              = "/aws/states/kr-data-pipeline-${var.env}"
  retention_in_days = 14

  tags = merge(local.base_tags, { Name = "kr-data-pipeline-sfn-logs-${var.env}" })
}

# -----------------------------------------------------------------------------
# IAM Role — Step Functions execution role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "sfn_execution_role" {
  name = "kr-data-pipeline-sfn-${var.env}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.base_tags, { Name = "kr-data-pipeline-sfn-role-${var.env}" })
}

resource "aws_iam_role_policy" "sfn_execution_policy" {
  name = "kr-data-pipeline-sfn-policy-${var.env}"
  role = aws_iam_role.sfn_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Invoke all 4 pipeline Lambda functions
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.kr_pipeline_transform.arn,
          aws_lambda_function.kr_pipeline_image.arn,
          aws_lambda_function.kr_pipeline_loader.arn,
          aws_lambda_function.kr_pipeline_vector.arn,
        ]
      },
      {
        # CloudWatch Logs write for execution logging
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# State Machine definition
# -----------------------------------------------------------------------------
resource "aws_sfn_state_machine" "kr_data_pipeline" {
  name     = "kr-data-pipeline-${var.env}"
  role_arn = aws_iam_role.sfn_execution_role.arn

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_logs.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  definition = jsonencode({
    Comment = "KR Data Pipeline - V2 load/vector orchestration"
    StartAt = "CheckVectorOnly"
    States = {
      CheckVectorOnly = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.run_vector_only"
            BooleanEquals = true
            Next          = "VisitorStatsCoverageGate"
          }
        ]
        Default = "CheckSkipTransform"
      }

      CheckSkipTransform = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.run_legacy_transform"
            BooleanEquals = true
            Next          = "TransformStage"
          }
        ]
        Default = "BuildCityList"
      }

      # -----------------------------------------------------------------
      # TransformStage: Map State — invoke kr-pipeline-transform per city
      # -----------------------------------------------------------------
      TransformStage = {
        Type           = "Map"
        ItemsPath      = "$.city_files"
        MaxConcurrency = 10
        ResultPath     = "$.transform_results"
        Next           = "BuildCityList"
        Iterator = {
          StartAt = "InvokeTransform"
          States = {
            InvokeTransform = {
              Type     = "Task"
              Resource = aws_lambda_function.kr_pipeline_transform.arn
              End      = true
              Retry = [
                {
                  ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.SdkClientException"]
                  MaxAttempts     = 2
                  IntervalSeconds = 3
                  BackoffRate     = 2
                }
              ]
            }
          }
        }
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error_info"
            Next        = "HandleFailure"
          }
        ]
      }

      # -----------------------------------------------------------------
      # BuildCityList: Pass state — constructs city_list for ImageStage
      # -----------------------------------------------------------------
      BuildCityList = {
        Type    = "Pass"
        Next    = "ImageStage"
        Comment = "Constructs city_list from S3 processed/{date}/passed/ file listing"
      }

      # -----------------------------------------------------------------
      # ImageStage: Map State — invoke kr-pipeline-image per city
      # -----------------------------------------------------------------
      ImageStage = {
        Type           = "Map"
        ItemsPath      = "$.city_list"
        MaxConcurrency = 10
        ResultPath     = "$.image_results"
        Next           = "AggregateReviewManifest"
        Iterator = {
          StartAt = "InvokeImageProcessor"
          States = {
            InvokeImageProcessor = {
              Type     = "Task"
              Resource = aws_lambda_function.kr_pipeline_image.arn
              End      = true
              Retry = [
                {
                  ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.SdkClientException"]
                  MaxAttempts     = 1
                  IntervalSeconds = 5
                  BackoffRate     = 2
                }
              ]
            }
          }
        }
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error_info"
            Next        = "HandleFailure"
          }
        ]
      }

      # -----------------------------------------------------------------
      # AggregateReviewManifest: invoke kr-pipeline-image (aggregate_review)
      # -----------------------------------------------------------------
      AggregateReviewManifest = {
        Type     = "Task"
        Resource = aws_lambda_function.kr_pipeline_image.arn
        Parameters = {
          command           = "aggregate_review"
          "bucket.$"        = "$.bucket"
          "ingest_date.$"   = "$.ingest_date"
          "image_results.$" = "$.image_results"
        }
        ResultPath = "$.review_manifest"
        Next       = "LoadStage"
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error_info"
            Next        = "HandleFailure"
          }
        ]
      }

      # -----------------------------------------------------------------
      # LoadStage: invoke kr-pipeline-loader (load command)
      # -----------------------------------------------------------------
      LoadStage = {
        Type     = "Task"
        Resource = aws_lambda_function.kr_pipeline_loader.arn
        Parameters = {
          command         = "load"
          "bucket.$"      = "$.bucket"
          "ingest_date.$" = "$.ingest_date"
          table_name      = var.domain_dynamodb_table_name_v2
        }
        ResultPath = "$.load_results"
        Next       = "VisitorStatsCoverageGate"
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.SdkClientException"]
            MaxAttempts     = 2
            IntervalSeconds = 5
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error_info"
            Next        = "HandleFailure"
          }
        ]
      }

      VisitorStatsCoverageGate = {
        Type     = "Task"
        Resource = aws_lambda_function.kr_pipeline_vector.arn
        Parameters = {
          command           = "preflight"
          table_name        = var.domain_dynamodb_table_name_v2
          entity_index_name = "EntityTypeDomainIndex"
        }
        ResultPath = "$.data_gates"
        Next       = "VisitorStatsCoverageChoice"
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.SdkClientException"]
            MaxAttempts     = 2
            IntervalSeconds = 5
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error_info"
            Next        = "HandleFailure"
          }
        ]
      }

      VisitorStatsCoverageChoice = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.data_gates.summary.visitor_statistics.coverage_ok"
            BooleanEquals = true
            Next          = "EnrichmentFieldLoadingGate"
          }
        ]
        Default = "VisitorStatsCoverageFailed"
      }

      EnrichmentFieldLoadingGate = {
        Type = "Choice"
        Choices = [
          {
            Variable     = "$.data_gates.summary.enrichment.mode"
            StringEquals = "enrichment-complete"
            Next         = "VectorPlanStage"
          },
          {
            Variable     = "$.data_gates.summary.enrichment.mode"
            StringEquals = "non-enrichment-complete"
            Next         = "VectorPlanStage"
          }
        ]
        Default = "EnrichmentFieldLoadingFailed"
      }

      EnrichmentFieldLoadingFailed = {
        Type = "Pass"
        Result = {
          error = "EnrichmentFieldLoadingGateFailed"
          cause = "enrichment field loading gate did not return a recognized mode"
        }
        ResultPath = "$.error_info"
        Next       = "HandleFailure"
      }

      VisitorStatsCoverageFailed = {
        Type = "Pass"
        Result = {
          error = "VisitorStatisticsCoverageFailed"
          cause = "visitor_statistics coverage gate did not pass"
        }
        ResultPath = "$.error_info"
        Next       = "HandleFailure"
      }

      VectorPlanStage = {
        Type     = "Task"
        Resource = aws_lambda_function.kr_pipeline_vector.arn
        Parameters = {
          command                            = "plan"
          table_name                         = var.domain_dynamodb_table_name_v2
          entity_index_name                  = "EntityTypeDomainIndex"
          vector_bucket                      = var.vector_bucket_name
          index_name                         = var.kr_vector_index_name
          batch_size                         = var.kr_vector_batch_size
          "enrichment_mode.$"                = "$.data_gates.summary.enrichment.mode"
          "visitor_statistics_coverage_ok.$" = "$.data_gates.summary.visitor_statistics.coverage_ok"
        }
        ResultPath = "$.vector_plan"
        Next       = "VectorBatchStage"
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.SdkClientException"]
            MaxAttempts     = 2
            IntervalSeconds = 5
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.vector_error"
            Next        = "GenerateReport"
          }
        ]
      }

      VectorBatchStage = {
        Type           = "Map"
        ItemsPath      = "$.vector_plan.batches"
        MaxConcurrency = var.kr_vector_map_max_concurrency
        ResultPath     = "$.vector_batch_results"
        Next           = "VectorAggregateStage"
        Iterator = {
          StartAt = "InvokeVectorWorker"
          States = {
            InvokeVectorWorker = {
              Type     = "Task"
              Resource = aws_lambda_function.kr_pipeline_vector.arn
              Parameters = {
                command   = "worker"
                "batch.$" = "$"
              }
              End = true
              Retry = [
                {
                  ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.SdkClientException"]
                  MaxAttempts     = 2
                  IntervalSeconds = 5
                  BackoffRate     = 2
                }
              ]
            }
          }
        }
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.vector_error"
            Next        = "GenerateReport"
          }
        ]
      }

      VectorAggregateStage = {
        Type     = "Task"
        Resource = aws_lambda_function.kr_pipeline_vector.arn
        Parameters = {
          command           = "aggregate"
          "batch_results.$" = "$.vector_batch_results"
          "entity_counts.$" = "$.vector_plan.summary.entity_counts"
        }
        ResultPath = "$.vector_results"
        Next       = "GenerateReport"
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.SdkClientException"]
            MaxAttempts     = 1
            IntervalSeconds = 5
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.vector_error"
            Next        = "GenerateReport"
          }
        ]
      }

      # -----------------------------------------------------------------
      # GenerateReport: invoke kr-pipeline-image (generate_report command)
      # -----------------------------------------------------------------
      GenerateReport = {
        Type     = "Task"
        Resource = aws_lambda_function.kr_pipeline_image.arn
        Parameters = {
          command               = "generate_report"
          "bucket.$"            = "$.bucket"
          "ingest_date.$"       = "$.ingest_date"
          "execution_context.$" = "$"
        }
        ResultPath = "$.report"
        Next       = "Success"
      }

      # -----------------------------------------------------------------
      # HandleFailure: Pass state — captures error context, routes to report
      # -----------------------------------------------------------------
      HandleFailure = {
        Type       = "Pass"
        ResultPath = "$.failure_info"
        Next       = "GenerateReport"
      }

      # -----------------------------------------------------------------
      # Success: terminal state
      # -----------------------------------------------------------------
      Success = {
        Type = "Succeed"
      }
    }
  })

  tags = merge(local.base_tags, { Name = "kr-data-pipeline-${var.env}" })

  depends_on = [
    aws_iam_role_policy.sfn_execution_policy,
    aws_cloudwatch_log_group.sfn_logs,
  ]
}
