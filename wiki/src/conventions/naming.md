# Naming

Python 코드 작성 시 사용하는 이름 규칙을 정의합니다.

## Python

- 변수명: `snake_case`
- 함수명: `snake_case`
- 메서드명: `snake_case`
- 클래스명: `PascalCase`
- 상수명: `UPPER_SNAKE_CASE`
- 모듈 파일명: `snake_case.py`
- 패키지 디렉터리명: `snake_case`
- 테스트 파일명: `test_{target_name}.py`

예시:

```python
MAX_RETRY_COUNT = 3

user_profile = get_user_profile(user_id)


class UserProfileSerializer:
    pass
```

## Private Names

외부에서 직접 사용하지 않는 내부 함수, 메서드, 변수는 앞에 `_`를 붙입니다.

```python
def _build_prompt_context(user_input: str) -> dict:
    return {"user_input": user_input}
```

## Boolean Names

Boolean 값은 의미가 분명하도록 `is_`, `has_`, `can_`, `should_` prefix를 사용합니다.

```python
is_active = True
has_permission = False
can_retry = True
should_create_log = False
```

## Collection Names

list, tuple, queryset 등 여러 값을 담는 이름은 복수형을 사용합니다.

```python
users = []
drafts = []
interview_questions = []
```
