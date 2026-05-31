# SKN26 Project Template Repository

SKN26 4차 프로젝트부터 최종 프로젝트까지 공통으로 사용할 수 있는 템플릿 저장소입니다.

아직 기술 스택은 확정하지 않았으며, 프로젝트를 시작할 때 필요한 기본 디렉터리, 문서, 협업 규칙을 먼저 정리하는 것을 목적으로 합니다.

## Purpose

- 4차 프로젝트부터 최종 프로젝트까지 반복해서 사용할 기본 저장소 구조를 제공합니다.
- 프로젝트별 기술 스택이 달라져도 공통으로 필요한 문서와 협업 규칙을 유지합니다.
- Git flow, commit convention, naming, code style, API contract, development process를 wiki로 관리합니다.
- 팀원이 새 프로젝트에 합류했을 때 저장소 사용 기준을 빠르게 확인할 수 있게 합니다.

## Project Scope

이 템플릿은 다음 프로젝트 구간에서 사용합니다.

- SKN26 4차 프로젝트
- SKN26 최종 프로젝트

## Tech Stack

기술 스택은 프로젝트별 요구사항에 따라 결정합니다.

확정 후 이 영역에 다음 내용을 업데이트합니다.

- Backend:
- Frontend:
- Database:
- AI / Model:
- Infra:
- Collaboration:

## Structure

```text
.
├── .github/
│   └── workflows/
├── backend/
├── frontend/
├── database/
├── models/
├── docs/
├── wiki/
│   ├── book.toml
│   └── src/
│       ├── SUMMARY.md
│       ├── overview.md
│       ├── conventions.md
│       └── conventions/
│           ├── git-flow.md
│           ├── commit.md
│           ├── naming.md
│           └── code-style.md
├── README.md
└── LICENSE
```

## Directory Guide

- `backend/`: 백엔드 애플리케이션 코드
- `frontend/`: 프론트엔드 애플리케이션 코드
- `database/`: DB schema, migration, seed, ERD 관련 파일
- `models/`: AI 모델, 학습/추론 관련 파일
- `docs/`: 프로젝트 산출물, 외부 공유 문서
- `wiki/`: 팀 내부 규칙과 개발 컨벤션
- `.github/`: GitHub template, workflow, automation 설정

## Wiki

프로젝트 규칙은 `wiki/` 아래 mdBook 문서로 관리합니다.

주요 문서:

- Git flow
- Commit convention
- Naming convention
- Code style

## Getting Started

새 프로젝트에서 이 템플릿을 사용할 때는 다음 항목을 먼저 수정합니다.

1. 프로젝트명과 설명
2. 확정된 기술 스택
3. `wiki/book.toml`의 book title
4. `wiki/src/overview.md`의 프로젝트 개요
5. `wiki/src/conventions/`의 팀별 상세 규칙
6. `.github/workflows/`의 브랜치, secrets, 배포 조건

## mdBook

github acitons로 인해서 자동으로 deploy까지 가능합니다.
사용하는 branch는 docs입니다.

## GitHub Actions

이 저장소는 GitHub Actions workflow를 통해 다음 작업을 수행할 수 있도록 구성합니다.

- mdBook 기반 wiki 배포
- PR 코드 리뷰 자동화

프로젝트에 맞게 브랜치 이름, secrets, action 버전을 확인한 뒤 사용합니다.

## License

See [LICENSE](./LICENSE).
