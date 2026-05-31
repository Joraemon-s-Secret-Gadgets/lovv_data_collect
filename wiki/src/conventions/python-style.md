# Python Style

Python 파일 작성 시 사용하는 개발 규칙을 정의합니다.

## File Header and Footer

개발 시 새로 생성하거나 주요 변경이 발생한 Python 파일에는 file header와 file footer를 작성합니다.

### File Header

file header는 이 파일이 어떤 역할을 하는지 설명합니다.

작성 기준:

- 파일 최상단에 module docstring으로 작성합니다.
- 파일의 책임과 사용되는 계층을 짧게 설명합니다.
- 구현 세부사항보다 파일의 목적을 설명합니다.
- 단순 `__init__.py`나 re-export 파일처럼 역할이 명확한 파일은 생략할 수 있습니다.

예시:

```python
"""
Draft generation API views.

This file handles draft generation request/response flow and delegates
business logic to draft services.
"""
```

### File Footer

file footer는 파일의 주요 변경 이력을 기록합니다.

작성 기준:

- 파일 최하단에 주석으로 작성합니다.
- 모든 커밋을 기록하지 않고, 파일 책임이 바뀌는 주요 변경만 기록합니다.
- 날짜는 `YYYY-MM-DD` 형식을 사용합니다.
- GitHub Issue가 있다면 issue 번호를 함께 기록합니다.

예시:

```python
# File History
# 2026-04-29: Created draft generation API view. (#45)
# 2026-05-02: Split validation into request serializer. (#52)
```

## Type Hint

Python 코드는 type hint를 명확하게 작성합니다.

작성 기준:

- 함수와 메서드는 모든 인자와 반환값에 type hint를 작성합니다.
- 반환값이 없는 함수는 `-> None`을 명시합니다.
- list, dict, tuple, set은 내부 타입까지 작성합니다.
- 값이 없을 수 있으면 `Optional[T]` 또는 `T | None`을 명시합니다.
- 여러 타입을 허용해야 하면 `Union` 또는 `|`를 사용하되, 가능한 한 타입 수를 줄입니다.
- `Any`는 외부 라이브러리 응답처럼 타입을 확정하기 어려운 경우에만 사용합니다.
- 복잡한 dict 구조는 `TypedDict`, `dataclass`, `pydantic` model 등 명시적인 타입으로 분리합니다.
- 외부 API 응답, 설정값, 요청/응답 payload처럼 경계가 있는 데이터는 Pydantic 모델로 검증합니다.
- 타입 별칭, `TypedDict`, `Protocol`, `Literal`, `Final` 등은 `typing`을 활용해 의미를 명확히 합니다.

권장 import:

```python
from typing import Final, Literal, Protocol, TypedDict

from pydantic import BaseModel, Field
```

좋은 예:

```python
def get_user_profile(user_id: int) -> UserProfile:
    ...


def update_user_tags(user_id: int, tags: list[str]) -> None:
    ...


def find_draft(draft_id: int) -> Draft | None:
    ...
```

Pydantic 활용 예:

```python
class DraftCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    category: Literal["resume", "cover_letter"]


class DraftCreateResponse(BaseModel):
    draft_id: int
    status: Literal["created"]


def create_draft(payload: DraftCreateRequest) -> DraftCreateResponse:
    ...
```

`typing` 활용 예:

```python
MAX_RETRY_COUNT: Final[int] = 3


class SupportsGenerate(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class DraftMetadata(TypedDict):
    title: str
    category: str
    owner_id: int
```

피해야 할 예:

```python
def get_user_profile(user_id):
    ...


def update_user_tags(user_id: int, tags: list):
    ...


def find_draft(draft_id: int):
    ...
```
