# Commit

커밋 메시지는 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)을 기준으로 작성합니다.

## Purpose

- 커밋 히스토리에서 변경 목적을 빠르게 파악합니다.
- changelog, release note, version bump 자동화에 사용할 수 있는 형식을 유지합니다.
- GitHub Issue와 커밋을 명확히 연결합니다.

## Format

```text
<type>[optional scope][optional !]: <description>

[optional body]

[optional footer(s)]
```

예시:

```text
feat(api): add draft generation endpoint

Add a new draft generation endpoint for resume content.
The endpoint validates request data through a dedicated serializer
and delegates generation logic to the draft service.

Closes #45
```

## Header

Header는 커밋의 변경 목적을 한 줄로 표현합니다.

```text
<type>[optional scope][optional !]: <description>
```

Header 구성:

| 항목 | 필수 여부 | 설명 | 예시 |
|---|---:|---|---|
| `type` | 필수 | 변경 목적 | `feat`, `fix`, `docs` |
| `scope` | 선택 | 변경 영역 | `api`, `auth`, `wiki` |
| `!` | 선택 | breaking change 표시 | `feat(api)!:` |
| `description` | 필수 | 변경 요약 | `add draft generation endpoint` |

### Type

`type`은 커밋의 목적을 나타냅니다.

- `feat`: 새로운 기능 추가
- `fix`: 버그 수정
- `docs`: 문서 변경
- `style`: 포맷팅, 공백, 세미콜론 등 동작 변경 없는 수정
- `refactor`: 기능 변경 없는 코드 구조 개선
- `perf`: 성능 개선
- `test`: 테스트 추가 또는 수정
- `build`: 빌드 시스템 또는 외부 의존성 변경
- `ci`: GitHub Actions 등 CI 설정 변경
- `chore`: 기타 유지보수 작업
- `revert`: 이전 커밋 되돌리기

`feat`는 minor release, `fix`는 patch release에 대응할 수 있습니다.
breaking change가 포함되면 type과 관계없이 major release 대상이 될 수 있습니다.

### Scope

`scope`는 변경된 영역을 나타내는 선택 항목입니다.

권장 scope:

- `api`
- `auth`
- `user`
- `draft`
- `interview`
- `redux`
- `ui`
- `db`
- `wiki`
- `actions`

예시:

```text
fix(auth): refresh access token on 401 response
docs(wiki): add commit convention
ci(actions): deploy wiki to pages
```

### Description

- 명령형 현재 시제로 작성합니다.
- 첫 글자는 소문자를 사용합니다.
- 마침표를 붙이지 않습니다.
- 한 줄로 변경 내용을 요약합니다.

좋은 예:

```text
feat(api): add draft generation endpoint
```

나쁜 예:

```text
feat(api): Added draft generation endpoint.
```

## Body

body는 선택 항목이지만, 변경 이유나 맥락이 필요한 경우 작성합니다.

작성 기준:

- description 다음에 한 줄을 비우고 작성합니다.
- 무엇을 바꿨는지보다 왜 바꿨는지를 우선 설명합니다.
- 여러 문단을 사용할 수 있습니다.
- 구현 세부사항은 리뷰에 필요한 수준만 작성합니다.

예시:

```text
fix(auth): retry request after token refresh

Access tokens can expire while the user is still active.
Previously, the first 401 response immediately logged out the user
even when a valid refresh token existed.

This change retries the original request after a successful refresh
and logs out only when refresh fails.

Fixes #81
```

## Footer

footer는 GitHub Issue, reviewer, breaking change 등 메타데이터를 작성합니다.

Footer 구성:

| 항목 | 필수 여부 | 설명 | 예시 |
|---|---:|---|---|
| Issue close token | 선택 | GitHub Issue 자동 종료 | `Closes #45` |
| Issue reference token | 선택 | 관련 GitHub Issue 참조 | `Refs #92` |
| `BREAKING CHANGE` | breaking change 시 필수 | 하위 호환성이 깨지는 변경 설명 | `BREAKING CHANGE: response schema changed` |
| Reviewer token | 선택 | 리뷰어 기록 | `Reviewed-by: username` |
| Co-author token | 선택 | 공동 작업자 기록 | `Co-authored-by: name <email>` |
| Revert reference | revert 시 권장 | 되돌린 커밋 참조 | `Refs: abc1234` |

GitHub Issue 연결:

```text
Closes #45
Fixes #81
Refs #92
```

- `Closes`: 이 커밋 또는 PR이 issue를 완료할 때 사용합니다.
- `Fixes`: 버그 issue를 해결할 때 사용합니다.
- `Refs`: 관련은 있지만 자동 close하지 않을 때 사용합니다.

## Breaking Change

하위 호환성이 깨지는 변경은 반드시 명시합니다.

방법 1: header에 `!` 사용

```text
feat(api)!: change draft response schema

Closes #120
```

방법 2: footer에 `BREAKING CHANGE:` 사용

```text
feat(api): change draft response schema

The draft response now wraps generated content in the data object.

BREAKING CHANGE: clients must read generated content from data.content
Closes #120
```

## Examples

### Feature

```text
feat(api): add draft generation endpoint

Users need an API for generating resume draft content from form input.
The endpoint validates request data through a create serializer and
delegates generation logic to the draft service.

Closes #45
```

### Fix

```text
fix(auth): retry original request after token refresh

The client previously logged out immediately when an access token expired.
This caused active users to lose their session even when the refresh token
was still valid.

The axios interceptor now refreshes the token once, retries the original
request, and dispatches logout only when refresh fails.

Fixes #81
```

### Test

```text
test(user): cover user profile permission cases

User profile access depends on authentication and ownership checks.
Add API tests for unauthenticated requests, owner access, and forbidden
access from another user.

Refs #92
```

### Docs

```text
docs(wiki): document commit message convention

The team needs a shared commit format before enabling stricter review
and release automation.

Add Conventional Commits format, allowed types, body guidance, footer
rules, and GitHub Issue examples.

Closes #103
```

### CI

```text
ci(actions): deploy wiki only after mdbook build

The wiki deployment should run only when mdBook content changes.
Limit the workflow trigger to the wiki path and upload the generated
book directory as a Pages artifact.

Closes #110
```

### Breaking Change

```text
feat(api)!: replace draft response format

The response format is aligned with the project-wide API contract.
Clients must read draft content from data.content instead of content.

BREAKING CHANGE: draft content moved from content to data.content
Closes #120
```
