# TourKoreaDomainData 웹 조회기 Spec

## User Request Original

AWS Dynamo DB에 적재되어있는 DB를 조회할 수 있는 웹을 하나 만들어야해. 검색 기능과 컬럼 명으로 Pill 형태로 찾도록

Follow-up:

- 워크 스페이스 새로 만들어서 해
- TourKoreaDomainData야
- 다 한글로 바꿔
- GSI 조회도 넣어

## Structured Agent Contract

현재 저장소 안에 `TourKoreaDomainData` DynamoDB 테이블을 읽기 전용으로 조회하는 독립형 웹 도구를 추가한다.

UI는 다음 기능을 제공해야 한다.

- 키워드 검색
- 컬럼명 Pill 선택 검색
- GSI 목록 확인과 GSI query 조회
- 결과 테이블과 행별 JSON 상세 보기
- 로딩, 오류, 빈 결과, 성공 상태

백엔드는 다음 조건을 지켜야 한다.

- AWS 자격 증명과 DynamoDB 접근은 서버 측에만 둔다.
- 기본 DynamoDB 테이블은 `TourKoreaDomainData`로 둔다.
- 컬럼 목록, 일반 검색, GSI 목록, GSI query용 읽기 전용 API를 제공한다.
- scan 작업은 페이지 수와 페이지 크기를 제한해 비용 폭주를 막는다.
- 실제 비밀값을 코드나 Git에 커밋하지 않는다.

## 구조

- `frontend/`: 정적 HTML, CSS, JavaScript UI
- `backend/`: Python Lambda handler, DynamoDB 조회 로직, 로컬 개발 서버
- `template.yaml`: 읽기 전용 API 배포용 AWS SAM template
- `events/`: Lambda proxy event 샘플

프론트엔드는 백엔드 API만 호출하며 AWS SDK 또는 AWS 자격 증명을 포함하지 않는다.

## API 계약

### `GET /api/columns`

제한된 sample scan으로 top-level DynamoDB attribute 이름을 반환한다.

Query params:

- `sampleSize`: 선택 integer, 기본값 `50`, 최대 `200`

Response:

```json
{
  "tableName": "TourKoreaDomainData",
  "columns": ["PK", "SK", "city_name"],
  "sampleSize": 50,
  "authMode": "required"
}
```

### `GET /api/search`

제한된 scan으로 item을 검색한다. 내부 확인과 디버깅용이며 대량 검색용 프로덕션 검색 인덱스가 아니다.

Query params:

- `q`: 선택 검색어, 최대 `200`자
- `column`: 선택 top-level attribute 이름. 있으면 해당 컬럼 안에서만 검색한다.
- `mode`: 선택 `contains` 또는 `equals`, 기본값 `contains`
- `limit`: 선택 결과 개수, 기본값 `25`, 최대 `100`
- `cursor`: 이전 응답에서 받은 opaque cursor

Response:

```json
{
  "tableName": "TourKoreaDomainData",
  "items": [],
  "columns": [],
  "count": 0,
  "scannedCount": 0,
  "nextCursor": null,
  "searchedPages": 1,
  "scanLimitReached": false
}
```

### `GET /api/indexes`

`DescribeTable` 결과에서 GSI 이름, key schema, projection 정보를 반환한다.

Response:

```json
{
  "tableName": "TourKoreaDomainData",
  "indexes": [
    {
      "indexName": "GSI1",
      "keySchema": [
        {"attributeName": "city_key", "keyType": "HASH"},
        {"attributeName": "domain_sort_key", "keyType": "RANGE"}
      ],
      "projectionType": "ALL"
    }
  ]
}
```

### `GET /api/query-index`

선택한 GSI로 DynamoDB `Query`를 실행한다.

Query params:

- `indexName`: 필수 GSI 이름. 예: `GSI1`
- `partitionValue`: 필수 partition key 값. 예: `CITY#Andong`
- `sortMode`: 선택 정렬 키 조건. `equals`, `begins_with`, `between`, `gt`, `gte`, `lt`, `lte`
- `sortValue`: 선택 정렬 키 시작/비교 값
- `sortValueTo`: `between` 조건의 끝 값
- `limit`: 선택 결과 개수, 기본값 `25`, 최대 `100`
- `cursor`: 이전 응답에서 받은 opaque cursor

Response:

```json
{
  "tableName": "TourKoreaDomainData",
  "indexName": "GSI1",
  "keySchema": [],
  "items": [],
  "columns": [],
  "count": 0,
  "scannedCount": 0,
  "nextCursor": null,
  "queryType": "gsi"
}
```

## 보안

- DynamoDB 접근은 서버 측에서만 수행한다.
- SAM 권한은 `TourKoreaDomainData`에 대한 `DescribeTable`, `Scan`, `Query`로 제한한다.
- 선택 환경변수 `VIEWER_ACCESS_TOKEN`이 있으면 `Authorization: Bearer <token>`을 요구한다.
- 공개 배포 시 Cognito 또는 API Gateway Authorizer 같은 실제 인증을 별도로 붙여야 한다.

## 수용 기준

- 기존 파이프라인 코드와 독립적인 `viewer/` 작업 공간이 있다.
- UI는 한국어로 표시된다.
- 컬럼명이 클릭 가능한 Pill 형태로 표시된다.
- 전체 값 검색 또는 선택한 컬럼 검색을 실행할 수 있다.
- GSI1, GSI2, GSI3 같은 테이블 GSI 목록을 불러오고 query 조회를 실행할 수 있다.
- 결과가 테이블로 표시되고 행별 JSON 상세를 열 수 있다.
- 백엔드 기본 테이블은 `TourKoreaDomainData`다.
- 로컬 mock 모드는 AWS 자격 증명 없이 동작한다.
- 기본 백엔드 테스트는 `boto3` 없이 통과한다.
