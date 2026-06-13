# TourKoreaDomainData 웹 조회기 Tasks

## Task 1: 독립 작업 공간 추가

- DynamoDB 조회기 전용 `viewer/` 폴더를 추가한다.
- 기존 데이터 수집, 전처리, 적재 코드와 동작을 변경하지 않는다.
- README, 환경변수 예시, 실행 안내를 추가한다.

## Task 2: 읽기 전용 DynamoDB 백엔드

- `GET /api/columns`, `GET /api/search`, `GET /api/indexes`, `GET /api/query-index`용 Python Lambda handler를 추가한다.
- DynamoDB와 로컬 mock data를 같은 인터페이스로 다루는 repository 계층을 둔다.
- scan 제한, query limit, cursor encoding, Decimal-safe JSON serialization, CORS, 선택 bearer-token gate를 추가한다.
- 검색 필터, cursor, GSI 조회 단위 테스트를 추가한다.

## Task 3: 한국어 검색 UI

- 키워드 검색, 컬럼 Pill, 검색 방식, 표시 개수, GSI 조회 폼, 로딩/오류/빈 결과 상태, 결과 테이블을 제공하는 정적 웹 UI를 추가한다.
- AWS 자격 증명과 DynamoDB 접근 정보를 브라우저 코드에 넣지 않는다.
- 로컬 mock 서버와 배포된 API base URL에서 모두 동작할 수 있게 한다.

## Task 4: SAM 배포 계약

- Lambda와 HTTP API용 SAM template을 추가한다.
- `TourKoreaDomainData`와 해당 GSI에 대한 읽기 전용 DynamoDB 권한만 부여한다.
- 비밀값은 parameter 또는 environment variable로만 전달하고 source code에는 넣지 않는다.

## 검증

- `python3 -m unittest discover -s backend/tests`
- 로컬 mock smoke:
  - `MOCK_DATA_PATH=backend/mock-data/sample-items.json python3 backend/local_server.py`
  - `http://127.0.0.1:8787` 접속
