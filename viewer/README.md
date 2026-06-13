# TourKoreaDomainData 웹 조회기

`TourKoreaDomainData` DynamoDB 테이블을 읽기 전용으로 확인하는 독립형 웹 조회기입니다.

브라우저는 작은 백엔드 API와만 통신합니다. AWS 자격 증명과 DynamoDB 접근은 서버 측에만 유지합니다.

## 로컬 Mock 실행

```bash
cd viewer
MOCK_DATA_PATH=backend/mock-data/sample-items.json python3 backend/local_server.py
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:8787
```

## 백엔드 테스트

```bash
cd viewer
python3 -m unittest discover -s backend/tests
```

## 실제 AWS 조회 실행

실제 DynamoDB를 조회하려면 `MOCK_DATA_PATH`를 빼고, 셸 또는 실행 환경에 AWS 자격 증명을 구성한 뒤 실행합니다. 로컬 Python 환경에는 `boto3`가 필요합니다.

```bash
cd viewer
DYNAMODB_TABLE_NAME=TourKoreaDomainData AWS_REGION=us-east-1 AWS_PROFILE=skn26_final python3 backend/local_server.py
```

현재 데이터 파이프라인 조회 가이드는 아래 리소스를 기준으로 합니다.

- Region: `us-east-1`
- AWS Profile: `skn26_final`
- DynamoDB Table: `TourKoreaDomainData`
- GSI1: `city_key` + `domain_sort_key`
- GSI2: `province_key` + `domain_sort_key`
- GSI3: `entity_type` + `domain_sort_key`

## SAM 배포

```bash
cd viewer
sam build
sam deploy --guided \
  --parameter-overrides \
  DynamoTableName=TourKoreaDomainData \
  AllowedCorsOrigin=https://your-admin-domain.example \
  ViewerAccessToken=replace-with-random-admin-token
```

이 조회기를 공개 환경에 배포할 때는 Cognito 또는 API Gateway Authorizer 같은 실제 인증을 붙여야 합니다. 포함된 bearer token 검사는 내부 확인용 최소 보호 장치이며, 완전한 권한 관리 시스템이 아닙니다.

## API

- `GET /api/columns`
- `GET /api/search?q=keyword&column=name&mode=contains&limit=25`
- `GET /api/indexes`
- `GET /api/query-index?indexName=GSI1&partitionValue=CITY#Andong&sortMode=begins_with&sortValue=ATTRACTION#`

`/api/search`는 제한된 DynamoDB scan을 사용합니다. 내부 확인과 디버깅에는 충분하지만 대량 검색용 프로덕션 인덱스는 아닙니다. 운영 조회는 가능한 한 `PK`/`SK` 또는 GSI 기반 query를 우선 사용하십시오.
