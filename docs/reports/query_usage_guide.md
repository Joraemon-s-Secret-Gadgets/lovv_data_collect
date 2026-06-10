# 쿼리 사용 가이드

이 문서는 `02_lovv_data_collect`에서 현재 기준으로 사용하는 S3 키 패턴과 DynamoDB 조회 패턴을 정리합니다.

## 1. 기본 환경/자원
- Region: `us-east-1`
- AWS Profile: `skn26_final`
- S3 버킷: `lovv-data-pipeline-dev-925273580929`(Terraform 기본값)
- DynamoDB 테이블: `TourKoreaDomainData`
- 핵심 속성
  - PK: `PK`
  - SK: `SK`
  - GSI1 PK: `city_key`
  - GSI1 SK: `domain_sort_key`
  - GSI2 PK: `province_key`
  - GSI2 SK: `domain_sort_key`
  - GSI3 PK: `entity_type`
  - GSI3 SK: `domain_sort_key`

## 2. S3 조회(명령형)

### 2.1 원천(raw) 폴더
- 원천 업로드 키 패턴
  - `raw/KR/details/{YYYYMMDD}/{city}.json`
- 특정 날짜 원천 전체 조회
```bash
aws s3 ls s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260609/ --recursive --profile skn26_final --region us-east-1
```

### 2.2 가공(Processed) 폴더
- 처리 산출물 패턴
  - `processed/KR/domain/{YYYYMMDD}/{city}/summary.json`
- 특정 날짜 처리 결과 목록
```bash
aws s3 ls s3://lovv-data-pipeline-dev-925273580929/processed/KR/domain/20260609/ --recursive --profile skn26_final --region us-east-1
```
- manifest
  - `processed/KR/manifest/{run_id}/summary.json`

## 3. DynamoDB 조회 쿼리

### 3.1 도시 단위 전체 조회 (PK=도시)
- 파라미터:
  - `PK = CITY#Andong`
  - SK 정렬 키로 정렬/필터링 가능
```bash
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk":{"S":"CITY#Andong"}}' \
  --profile skn26_final --region us-east-1
```

### 3.2 특정 타입/월 통계만 필터링
- 월별 방문 통계 키는 `STAT#{YYYYMM}`
  - 예: `STAT#202501`
- 특정 월 통계 하나만 조회
```bash
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --key-condition-expression "PK = :pk AND SK = :sk" \
  --expression-attribute-values '{":pk":{"S":"CITY#Andong"},":sk":{"S":"STAT#202501"}}' \
  --profile skn26_final --region us-east-1
```

### 3.3 특정 콘텐츠 ID 조회
- 변환 규칙
  - 음식점: `RESTAURANT#{contentid}`
  - 관광지: `ATTRACTION#{contentid}`
  - 축제: `FESTIVAL#{contentid}`
- 쿼리
```bash
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --key-condition-expression "PK = :pk AND SK = :sk" \
  --expression-attribute-values '{":pk":{"S":"CITY#Andong"},":sk":{"S":"ATTRACTION#126157"}}' \
  --profile skn26_final --region us-east-1
```

### 3.4 도시별 도메인 조회(GSI1)
- `city_key = CITY#{city_name_en}`
- `domain_sort_key` prefix:
  - `RESTAURANT#`
  - `ATTRACTION#`
  - `FESTIVAL#`
  - `STAT#`
```bash
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --index-name GSI1 \
  --key-condition-expression "city_key = :city AND begins_with(domain_sort_key, :domain)" \
  --expression-attribute-values '{":city":{"S":"CITY#Andong"},":domain":{"S":"ATTRACTION#"}}' \
  --profile skn26_final --region us-east-1
```

### 3.5 도/광역 단위 도메인 조회(GSI2)
- `province_key = PROVINCE#{province}`
- 예: 경상북도 관광지만 조회
```bash
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --index-name GSI2 \
  --key-condition-expression "province_key = :province AND begins_with(domain_sort_key, :domain)" \
  --expression-attribute-values '{":province":{"S":"PROVINCE#경상북도"},":domain":{"S":"ATTRACTION#"}}' \
  --profile skn26_final --region us-east-1
```

### 3.6 entity type 기준 조회(GSI3)
- 전체 적재 데이터에서 특정 도메인만 조회할 때 사용한다.
```bash
aws dynamodb query \
  --table-name TourKoreaDomainData \
  --index-name GSI3 \
  --key-condition-expression "entity_type = :type" \
  --expression-attribute-values '{":type":{"S":"festival"}}' \
  --profile skn26_final --region us-east-1
```

## 4. Python(Boto3) 조회 예시

### 4.1 도시별 쿼리
```python
resp = ddb.query(
    TableName="TourKoreaDomainData",
    KeyConditionExpression="PK = :pk",
    ExpressionAttributeValues={":pk": {"S": "CITY#Andong"}},
)
```

### 4.2 정렬 키 범위 조회(최근 통계만 조회)
```python
resp = ddb.query(
    TableName="TourKoreaDomainData",
    KeyConditionExpression="PK = :pk AND SK BETWEEN :from AND :to",
    ExpressionAttributeValues={
        ":pk": {"S": "CITY#Andong"},
        ":from": {"S": "STAT#202501"},
        ":to": {"S": "STAT#202512"},
    },
)
```

## 5. 주의/운영 노트
- 현재 도메인 분리 적재의 운영 기준 테이블은 `TourKoreaDomainData`입니다.
- 기존 `TourKoreaData`는 이전 파이프라인 산출물과 비교할 때만 사용합니다.
- `kr-domain-loader`는 같은 `PK`/`SK`에 대해 `put_item`으로 덮어씁니다. 컬럼 구조가 바뀐 경우에는 테이블 item 삭제 후 전체 재적재가 더 안전합니다.
- 민감값(ACCESS KEY/SECRET)은 `~/.aws/credentials` 또는 세션 프로파일 기반으로 관리하고, 코드/문서에 직접 노출하지 않습니다.
- 배포/운영에서 `query` 대신 `scan`을 남발하면 비용이 증가할 수 있으므로 우선 PK/SK 패턴을 고정해 조회하십시오.
