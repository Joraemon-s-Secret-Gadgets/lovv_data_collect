# Code Style

## Django

### View

- View 함수 또는 메서드는 하나의 요청 흐름만 담당합니다.
- View가 80줄을 넘거나 분기와 비즈니스 로직이 많아지면 service 함수로 분리합니다.
- DB 조회, 외부 API 호출, 복잡한 조건 판단은 View에 직접 두지 않습니다.

### Serializer

- 요청 검증과 응답 직렬화 책임을 구분합니다.
- 생성/수정 요청 필드가 다르면 별도 Serializer로 분리합니다.
- Serializer 내부에 외부 API 호출이나 복잡한 비즈니스 로직을 넣지 않습니다.

### Apps Structure

백엔드는 계층 우선 구조를 사용하고, 각 계층 내부에서 도메인별 파일로 분리합니다.

이 구조는 serializer, view, service, test를 계층별로 빠르게 찾을 수 있게 하면서도 파일 단위로 도메인 경계를 유지합니다.

```text
apps/
  common/
    exceptions.py
    permissions.py
    responses.py
  models/
    __init__.py
    users.py
    drafts.py
    interviews.py
  serializers/
    __init__.py
    users.py
    drafts.py
    interviews.py
  views/
    __init__.py
    users.py
    drafts.py
    interviews.py
  services/
    __init__.py
    users.py
    drafts.py
    interviews.py
  urls/
    __init__.py
    users.py
    drafts.py
    interviews.py
  tests/
    users/
      test_user_api.py
      test_user_service.py
    drafts/
      test_draft_api.py
      test_draft_service.py
    interviews/
      test_interview_api.py
      test_interview_service.py
```

모델은 패키지로 분리하되, Django가 모델을 인식할 수 있도록 `apps/models/__init__.py`에서 명시적으로 import합니다.

```python
from .users import UserProfile
from .drafts import Draft
from .interviews import Interview
```

규칙:

- 새 도메인은 각 계층에 같은 이름의 파일을 추가합니다.
- View는 요청/응답 흐름만 담당하고, 비즈니스 로직은 service에 둡니다.
- Serializer는 입력 검증과 출력 직렬화에 집중합니다.
- 공통 응답, 예외, 권한 로직은 `common/`에 둡니다.
- 도메인 간 의존은 service 계층에서만 허용합니다.

## React

### Component

- 컴포넌트는 UI 표현 책임을 우선합니다.
- 컴포넌트가 150줄을 넘으면 하위 컴포넌트 분리를 검토합니다.
- API 호출, 복잡한 상태 계산, 부수 효과는 custom hook으로 분리합니다.

### Custom Hook

- 재사용되는 상태 로직은 custom hook으로 분리합니다.
- API 요청, 폼 상태, 페이지 단위 상태 조합은 hook으로 캡슐화합니다.
- hook 이름은 `use`로 시작합니다.

### Redux Slice

- slice는 도메인 또는 기능 단위로 나눕니다.
- action, reducer, selector를 같은 slice 기준으로 관리합니다.
- 비동기 요청은 `createAsyncThunk` 또는 프로젝트 표준 API layer를 사용합니다.

예시:

```text
src/
  features/
    auth/
      authSlice.ts
      authSelectors.ts
      authThunks.ts
    draft/
      draftSlice.ts
      draftSelectors.ts
      draftThunks.ts
```
