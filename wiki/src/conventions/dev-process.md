# Development Process

## Test First

- 모든 기능 구현은 Unit Test 작성을 먼저 진행합니다.
- 테스트 없는 기능 구현은 허용하지 않습니다.
- 버그 수정은 재현 테스트를 먼저 작성한 뒤 수정합니다.
- 테스트가 실패하는 상태에서 리뷰를 요청하지 않습니다.

## Development Order

```text
테스트 작성 -> 구현 -> 로컬 검증 -> PR 생성 -> CI 통과 -> 리뷰 요청
```

## Django Test

- Django 테스트는 `pytest-django` 기반으로 작성합니다.
- API 테스트는 DRF test client 또는 프로젝트 표준 API client fixture를 사용합니다.
- DB가 필요한 테스트는 `pytest.mark.django_db`를 명시합니다.
- Serializer 검증, service 로직, permission, API 응답 상태를 분리해서 테스트합니다.

예시 테스트 범위:

- Serializer validation
- Service business logic
- API status code
- Authentication and permission
- Error response format

## React Test

- React 테스트는 Jest와 React Testing Library를 기반으로 작성합니다.
- 구현 세부사항보다 사용자 관점의 동작을 검증합니다.
- Redux가 필요한 컴포넌트는 test store wrapper를 사용합니다.
- API 요청은 mock server 또는 프로젝트 표준 mock adapter를 사용합니다.

예시 테스트 범위:

- Component rendering
- User interaction
- Form validation
- Loading, success, error state
- Redux state transition

## Coverage

- 전체 라인 커버리지 기준은 80% 이상을 목표로 합니다.
- 핵심 도메인 service, serializer, reducer, API client는 90% 이상을 목표로 합니다.
- 커버리지 수치보다 중요한 비즈니스 경로가 테스트에 포함됐는지 우선 확인합니다.

## Review Gate

- 테스트가 없거나 실패하는 PR은 리뷰 요청하지 않습니다.
- 새 기능은 정상 케이스와 실패 케이스 테스트를 모두 포함합니다.
- 버그 수정은 재발 방지 테스트를 포함합니다.
