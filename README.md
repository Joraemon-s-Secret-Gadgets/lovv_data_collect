# Lovv Data Collect

Lovv 서비스에서 사용할 도시, 관광지, 축제 데이터를 수집하고 AWS에 적재하기 위한 데이터 수집/파이프라인 저장소입니다.

현재 저장소는 한국(KR) 데이터를 중심으로 다음 흐름까지 구현되어 있습니다.

1. Wikipedia 및 TourAPI 기반 도시/상세 데이터 취득 보조 코드
2. `data/KR/details/*.json` 원본을 S3 Raw 영역에 업로드
3. Raw JSON을 음식점/관광지/축제 도메인 데이터로 전처리
4. 전처리 결과를 DynamoDB `TourKoreaDomainData`에 적재하는 도메인 로더
5. Terraform 기반 S3, DynamoDB, IAM, Lambda 배포 구성

## Overview

이 저장소는 PRD와 Spec을 기준으로 Phase 0, Phase 1 범위를 나누어 개발 중입니다.

- **Phase 0:** Terraform으로 S3 Raw 저장소, DynamoDB 테이블, Lambda 실행 권한, CloudWatch Log Group을 구성합니다.
- **Phase 1:** 수집된 KR 상세 JSON을 S3 Raw에 보존하고, Transform/Load 단계를 통해 DynamoDB 적재 가능한 형태로 처리합니다.

수집 데이터 원본은 로컬 생성 산출물 또는 참조 레포 산출물을 사용합니다. 현재 참조 레포는 `Gloveman/tour-api-korea`입니다.

## Tech Stack

- **Language:** Python 3.12
- **Package manager:** uv
- **Crawler libraries:** requests, beautifulsoup4
- **AWS SDK:** boto3
- **Infrastructure:** Terraform
- **AWS services:** S3, DynamoDB, Lambda, IAM, CloudWatch Logs
- **Testing:** pytest

## Project Structure

```text
.
├── crawling/
│   ├── JP/
│   ├── KR/
│   ├── pyproject.toml
│   └── uv.lock
├── data/
│   ├── JP/
│   └── KR/
├── docs/
│   └── specs/
├── infrastructure/
│   └── terraform/
├── src/
│   └── kr_details_pipeline/
├── viewer/
│   ├── backend/
│   ├── frontend/
│   └── template.yaml
├── wiki/
├── pyproject.toml
├── uv.lock
└── README.md
```

주요 디렉터리 역할은 다음과 같습니다.

- `crawling/`: 국가별 데이터 취득 코드입니다. 크롤러 전용 `uv` 프로젝트가 따로 있습니다.
- `data/`: 로컬 데이터 작업 공간입니다. 실제 수집 산출물과 캐시는 Git에 올리지 않습니다.
- `docs/specs/`: 데이터 파이프라인과 ELT 설계 문서입니다.
- `infrastructure/terraform/`: AWS 리소스 IaC입니다.
- `src/kr_details_pipeline/`: S3 Raw 업로드, Transform, Load, Lambda handler 코드입니다.
- `viewer/`: `TourKoreaDomainData` DynamoDB 테이블을 검색하고 GSI로 조회하는 읽기 전용 웹 조회기입니다.
- `wiki/`: 팀 규칙과 개발 컨벤션 문서입니다.

## Environment

루트 `.env`에는 실제 API 키를 넣을 수 있지만 Git에 커밋하지 않습니다. 필요한 형식은 [.env.example](./.env.example)을 기준으로 맞춥니다.

```env
TOUR_API_KEYS=decoded_tour_api_key_1,decoded_tour_api_key_2
```

Terraform은 `.env`를 자동으로 읽지 않습니다. `infrastructure/terraform/deploy.ps1` 또는 `TF_VAR_*` 환경변수를 사용합니다.

기본 AWS 설정은 현재 개발 기준으로 아래 값을 사용했습니다.

- `AWS_PROFILE`: `skn26_final`
- `aws_region`: `us-east-1`
- S3 bucket: `lovv-data-pipeline-dev-925273580929`
- DynamoDB table: `TourKoreaDomainData`

## Getting Started

루트 파이프라인 개발 환경은 아래 명령으로 준비합니다.

```powershell
uv sync --frozen
```

전역 uv 캐시 권한 문제가 있을 때는 워크스페이스 내부 캐시를 지정할 수 있습니다.

```powershell
$env:UV_CACHE_DIR = ".cache\uv"
uv sync --frozen
```

크롤러 전용 환경은 `crawling/` 폴더에서 따로 관리합니다.

```powershell
cd crawling
$env:UV_CACHE_DIR = "..\.cache\uv"
uv sync --frozen
```

## Commands

루트 파이프라인 테스트:

```powershell
.venv\Scripts\python.exe -m pytest src
```

크롤러 테스트:

```powershell
cd crawling
.venv\Scripts\python.exe -m pytest
```

전체 테스트를 루트 설정 기준으로 실행할 수도 있습니다.

```powershell
.venv\Scripts\python.exe -m pytest
```

웹 조회기 테스트:

```powershell
cd viewer
python -m unittest discover -s backend/tests
```

웹 조회기 로컬 Mock 실행:

```powershell
cd viewer
$env:MOCK_DATA_PATH = "backend/mock-data/sample-items.json"
python backend/local_server.py
```

Terraform 검증:

```powershell
cd infrastructure/terraform
terraform fmt -check
terraform validate
terraform plan
```

## Crawling

`crawling/` 폴더는 JP/KR 도시 데이터 취득 코드를 포함합니다.

- `crawling/KR/city_wikipedia_acquisition.py`: 한국 도시 기본 정보 취득
- `crawling/KR/tour_api_city_detail_acquisition.py`: TourAPI 도시 상세 데이터 취득
- `crawling/KR/tour_api_region_detail_acquisition.py`: 지역 단위 TourAPI 상세 데이터 취득
- `crawling/KR/tour_api_detail_harvester.py`: 참조 레포 산출물을 도시별 상세 JSON으로 정규화

크롤링 산출물은 `data/KR/details/`, `data/KR/detail_cache/` 같은 로컬 경로에 생성되며 Git에서 제외됩니다.

## Raw Ingest

S3 Raw 적재는 루트 패키지의 CLI로 실행합니다.

```powershell
.venv\Scripts\python.exe -m kr_details_pipeline.cli raw-ingest `
  --input-dir data/KR/details `
  --output-dir data/KR/ingest `
  --bucket lovv-data-pipeline-dev-925273580929 `
  --profile skn26_final `
  --region us-east-1 `
  --ingest-date 20260609
```

이 단계는 원본 JSON을 `raw/KR/details/<ingest-date>/` Prefix로 업로드하고, 재처리를 위한 checksum manifest를 생성합니다.

## Domain Preprocess and Load

Domain preprocess 단계는 Raw 상세 JSON을 음식점, 관광지, 축제, 도시 메타데이터, 방문 통계 item으로 분리합니다.

```powershell
.venv\Scripts\python.exe -m kr_details_pipeline.cli domain-preprocess `
  --raw-file data/KR/details/Andong.json `
  --output-dir data/KR/elt/andong `
  --table-name TourKoreaDomainData
```

AWS Lambda에서는 S3 Raw JSON을 직접 읽어 전처리 후 DynamoDB에 적재합니다.

```json
{
  "bucket": "lovv-data-pipeline-dev-925273580929",
  "raw_key": "raw/KR/details/20260609/Andong.json",
  "table_name": "TourKoreaDomainData",
  "processed_prefix": "processed/KR/domain",
  "write_processed": true
}
```

AWS Lambda에서는 다음 handler를 사용합니다.

- Domain loader: `kr_details_pipeline.handlers.domain_loader_handler.handler`

## Terraform

Terraform 코드는 `infrastructure/terraform/`에 있습니다.

현재 구성하는 주요 리소스:

- S3 bucket: Raw/Processed/Failed/Review/Quality Prefix를 사용하는 파이프라인 저장소
- DynamoDB: `TourKoreaDomainData`
- IAM Role/Policy: Lambda 실행 및 S3/DynamoDB 접근 권한
- CloudWatch Log Group: `kr-domain-loader`
- Lambda: `kr-domain-loader`

PowerShell에서 `.env` 기반으로 실행할 때:

```powershell
cd infrastructure/terraform
Copy-Item .env.example .env -Force
.\deploy.ps1 -Action plan
.\deploy.ps1 -Action apply
```

직접 환경변수로 실행할 때:

```powershell
cd infrastructure/terraform
$env:AWS_PROFILE = "skn26_final"
$env:TF_VAR_aws_profile = "skn26_final"
$env:TF_VAR_aws_region = "us-east-1"
$env:TF_VAR_env = "dev"
$env:TF_VAR_bucket_base_name = "lovv-data-pipeline"
$env:TF_VAR_domain_dynamodb_table_name = "TourKoreaDomainData"
terraform init
terraform plan
terraform apply
```

## Data and Git Hygiene

실제 수집 데이터, API 응답, Lambda ZIP, Terraform state, `.env`, 가상환경은 Git에 올리지 않습니다.

대표적으로 제외되는 항목:

- `.env`
- `.venv/`
- `crawling/.venv/`
- `data/KR/details/`
- `data/KR/detail_cache/`
- `data/KR/ingest/`
- `infrastructure/terraform/*.zip`
- `*.tfstate`
- `*.tfstate.lock.info`
- `tmp_*.py`
- `response*.json`

데이터 디렉터리 자체는 `.gitkeep`만 유지하고, 실제 데이터 파일은 로컬 또는 S3에서 관리합니다.

## Documentation

주요 설계 문서는 아래 파일을 기준으로 확인합니다.

- [docs/data_pipeline_prd.md](./docs/data_pipeline_prd.md)
- [docs/specs/data_pipeline_spec.md](./docs/specs/data_pipeline_spec.md)
- [docs/specs/kr_details_elt_spec.md](./docs/specs/kr_details_elt_spec.md)
- [infrastructure/terraform/README.md](./infrastructure/terraform/README.md)

## License

See [LICENSE](./LICENSE).
