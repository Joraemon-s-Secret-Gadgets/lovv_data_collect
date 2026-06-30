# KR Lambda/SFN Batch Reset Full Rebuild Approval Package - 2026-06-30

## 승인 요청 사항

Task 7 smoke 테스트 성공 후, 다음에 대한 명시적 사용자 승인을 요청합니다:

1. ✅ **전체 Step Functions 벡터 리빌드 실행 승인**
2. ✅ **비-dry-run 벡터 워커 쓰기 승인** (실제 S3 Vector 쓰기 허용)
3. ✅ **집계 실행 및 매니페스트 쓰기 승인**
4. ✅ **타겟 벡터 버킷/인덱스 확인**: lovv-vector-dev / kr-tour-domain-v2
5. ✅ **동시성 수준**: MaxConcurrency=5 (Step Functions Map 기준)
6. ✅ **재try 정책**: 지수 백오프, 최대 3회 재시도
7. ✅ **보호 사항 확인**: S3 Vector 인덱스 삭제/재생성 미승인

## Task 7 검증 증거 (승인 전제 조건)

- 방문자 통계 보존: 2,820 행, 커버리지 OK
- 풍부화 모드 보존: non-enrichment-complete
- 보호 리소스 무결성: DynamoDB/S3/S3 Vector 모두 no-op
- 플래너 스모크: visitor_statistics 제외, 5개 배치 생성
- 워커 드라이런 스모크: 타임아웃 없음, 실패 0
- post-apply 라이브 베리파이어: exit code 0 (올드 드리프트 해소)

## 실행 계획 (승인 시)

**Subtask 2: 승인된 전체 벡터 워크플로 실행 시작**
- Step Functions 상태 머신을 통해 전체 벡터 리빌드 트리거
- VectorBatchStage에서 Map 병렬 처리 (MaxConcurrency=5)
- 각 배치에 대해 kr-pipeline-vector Lambda 호출 (worker 모드, dry_run=false)

**Subtask 3: 진행 모니터링 및 승인된 범위 내 재시도**
- 배치 실행 상태 추적 (성공/실패/재시도 횟수)
- 실패한 배치에 대해 지수 백오프 재시도 적용 (최대 3회)
- CloudWatch 로그 및 메트릭을 통한 성능 모니터링

**Subtask 4: 출력 검증 및 보호 범위 확인**
- 최종 벡터 카운트 기록
- 샘플 쿼리 증거 수집 (가능한 경우)
- Aggregate 실행 시 매니페스트 경로 기록
- 보호 범위 재검증 (방문자 통계, 풍부화 필드, DynamoDB/S3/S3 Vector)

## 승인 조건

이 승인은 다음 조건 하에 유효합니다:
- 실행 시작 시각부터 4시간 이내에 작업이 시작되어야 함
- 중간에 방문자 통계가 2,820 미만으로 떨어지면 즉시 중단
- 풍부화 모드가 완료로 변경되어도 기존 비완전 상태를 기준으로 진행
- 보호 리소스에 삭제/재생성 시도가 감지되면 즉시 중단

## 실행자 주의 사항

- 전체 리빌드는 수시간 소요될 수 있음
- 중간 실패는 일반적이며, 승인된 재try 정책에 따라 처리됨
- 최종 결과는 작업 완료 후 TASK8_COMPLETION.md에 기록됨
- 완전하지 않은 결과라도 검증 가능한 증거를 남겨야 함

승인 시각: 2026-06-30 17:00 KST
승인자: 사용자 명시적 승인
