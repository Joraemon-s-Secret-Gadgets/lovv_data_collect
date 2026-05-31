# Git Flow

## Branch

- 기본 개발 브랜치는 `dev`를 사용합니다.
- 기능 브랜치는 `feature/` prefix를 사용합니다.
- 브랜치 이름에는 Jira 이슈 키를 포함하지 않습니다.
- 브랜치 이름은 구현하려는 기능이 드러나도록 작성합니다.

예시:

```text
feature/draft-generate-api
feature/rag-fallback
feature/interview-service
feature/user-profile-api
```

## Pull Request

- PR은 fork 또는 기능 브랜치에서 upstream `dev` 브랜치로 생성합니다.
- PR 제목에는 Jira 이슈 키를 포함하지 않습니다.
- PR 제목에는 `Feat:` 같은 타입 태그를 붙이지 않고, 기능 설명만 작성합니다.
- PR 제목은 영어로 작성합니다.
- GitHub Issue가 연결되어 있다면 PR 본문에만 연결합니다.
- PR은 테스트가 통과한 뒤 코드 리뷰를 요청합니다.

PR 제목 형식:

```text
{short English summary}
```

예시:

```text
Implement draft generation API
```

## PR 본문 템플릿

```markdown
## 요약
- 

## 작업 내용
- 

## 테스트 결과
- [ ] 로컬 실행 확인
- [ ] 단위 테스트 통과
- [ ] 통합 테스트 통과

## 리뷰 요청 사항
- 

## 이슈 연결
Closes #0
```
