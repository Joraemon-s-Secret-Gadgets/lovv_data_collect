# kr_image_uploader

KR 도시 **관광지 이미지**를 S3에 업로드하는 패키지입니다.

`kr_details_pipeline`의 raw 적재가 만든 도시 JSON
(`raw/KR/details/<날짜>/<City>.json`)을 읽어, 각 관광지·축제의 `firstimage`·`firstimage2`
URL을 뽑고, 한글 제목을 영문(로마자) 파일명으로 변환한 뒤 다음 경로로 업로드합니다.

```
s3://<버킷>/images/KR/<City>/<관광지영문이름>_<n>.<확장자>
```

`_1`은 `firstimage`, `_2`는 `firstimage2`입니다. 예: `images/KR/Cheorwon/Goseokjeong_1.jpg`.

## 구성

| 파일 | 역할 |
|------|------|
| `romanize.py` | 한글 → 영문 슬러그 변환 (국어의 로마자 표기법, 음절 단위) |
| `extract.py` | 도시 JSON에서 `firstimage`/`firstimage2` 대상 추출 |
| `s3_keys.py` | `images/KR/<City>/<이름>_<n>.<확장자>` 키 생성 |
| `download.py` | 이미지 HTTP 다운로드 (표준 라이브러리만 사용) |
| `uploader.py` | 다운로드 + `put_object` 오케스트레이션, 성공/실패 집계 |
| `cli.py` | 명령줄 진입점 |
| `tests/` | `unittest` 테스트 (네트워크·AWS 불필요) |

## 사용 방법

> **모든 명령은 `src/` 디렉터리에서 실행하세요.** 그래야 `kr_image_uploader` 패키지를 import할 수 있습니다.
> 실제 업로드에는 AWS 자격증명이 설정돼 있어야 하고(`aws configure`), 업로드는 boto3를 사용합니다.
>
> 수집한 raw JSON은 프로젝트 규칙에 따라 repo 루트의 **`data/`** 작업 공간에 저장합니다.
> `data/`는 Git에 올리지 않습니다. 아래 명령은 `src/`에서 실행한다고 가정하며, `..\data`가 repo 루트의 `data` 폴더입니다.

### 1) 도시 raw JSON 받기 (`data/` 로 저장)

```bash
aws s3 cp s3://lovv-data-pipeline-dev-925273580929/raw/KR/details/20260609/ ..\data\raw\KR\details\20260609\ --recursive
```

### 2) 미리보기 (다운로드·업로드 안 함, AWS 불필요)

먼저 `--dry-run`으로 올라갈 키 목록과 개수를 확인하는 것을 권장합니다.

```bash
# 한 도시 미리보기
python -m kr_image_uploader.cli --json ..\data\raw\KR\details\20260609\Cheorwon.json --city Cheorwon --dry-run

# 폴더 전체 미리보기
python -m kr_image_uploader.cli --dir ..\data\raw\KR\details\20260609 --dry-run
```

### 3) 실제 업로드

```bash
# 한 도시 업로드
python -m kr_image_uploader.cli --json ..\data\raw\KR\details\20260609\Cheorwon.json --city Cheorwon

# 폴더 전체 업로드 (도시명은 파일명에서 자동 추출)
python -m kr_image_uploader.cli --dir ..\data\raw\KR\details\20260609
```

### 옵션

- `--json` 단일 raw 도시 JSON 파일
- `--dir` `{City}.json` 파일들이 든 폴더 (`--json`과 둘 중 하나는 필수)
- `--city` 도시 폴더 이름 직접 지정 (생략 시 JSON 파일명을 사용)
- `--bucket` 대상 버킷 (기본값 `lovv-image-dev-925273580929`)
- `--prefix` 상위 경로 (기본값 `images/KR`)
- `--dry-run` 올라갈 키만 출력 (다운로드·업로드 안 함)

## 참고

- raw JSON 등 수집 데이터는 repo 루트의 `data/` 작업 공간에만 두고 Git에 올리지 않습니다.
  `src/` 패키지 폴더에는 데이터 파일을 두지 마세요.
- 이미지를 로컬에 저장하지 않습니다. `download.py`가 이미지를 **메모리(바이트)** 로만 받아서
  `uploader.py`가 곧장 S3로 `put_object` 합니다 (URL → 메모리 → S3). 작업 폴더에 이미지가 쌓이지 않습니다.
- 원본 URL이 죽은 경우(예: 404)는 `[FAIL]`로 표시하고 건너뛴 뒤 계속 진행합니다.
- 로마자 변환은 음절 단위라 모든 음운 동화 규칙을 구현하지는 않지만, 이름은 안정적이고
  고유하며 ASCII로만 만들어집니다. 받침 ㄹ + 모음 연음(예: `철원` → `Cheorwon`)은 반영돼 있습니다.
- 원본 이미지는 한국관광공사(VisitKorea, `tong.visitkorea.or.kr`)의 관광 사진이므로,
  외부에 공개 사용하기 전에 이용약관을 확인하세요.

## 업로드 점검 (실패 추적)

업로드 후, raw JSON에서 계산한 "올라가야 할 목록"과 실제 S3에 있는 목록을 비교해
도시별 실패 개수와 빠진 파일을 찾습니다. `--check-urls`를 붙이면 빠진 이미지 URL의
상태코드(예: 404 = 원본 사진 삭제됨)까지 확인해 원인을 알려줍니다.

```bash
# src/ 에서 실행 (boto3 + AWS 자격증명 필요)
python -m kr_image_uploader.audit --dir ..\data\raw\KR\details\20260609

# 원인까지 확인 (빠진 URL을 HTTP GET으로 점검 -> 404 = 원본 없음, 200 = 일시 실패라 복구 가능)
python -m kr_image_uploader.audit --dir ..\data\raw\KR\details\20260609 --check-urls
```

도시별 빠진 파일 목록과, 맨 끝에 `City / exp(예상) / ok(성공) / fail(실패)` 요약 표가 출력됩니다.

### 빠진 이미지만 재시도

일시적 오류(타임아웃 등)로 빠진 이미지를 다시 받아 올립니다. **빠진 것만** 시도하므로
이미 올라간 객체는 건드리지 않고, 원본이 없는 404는 자동으로 건너뜁니다.

```bash
python -m kr_image_uploader.audit --dir ..\data\raw\KR\details\20260609 --retry-missing
```

도시별로 `[RECOVERED]`(복구됨) / `[skip 404]`(원본 없음)이 출력되고, 요약 표에 `recov`(복구 수) 열이 추가됩니다.

### 실패 목록 CSV로 저장

빠진 이미지 목록을 CSV로 남깁니다 (`city, content_id, title, filename, url, status`).
`--out`을 쓰면 각 URL의 상태코드도 자동으로 확인해 채웁니다. PR 증빙·기록용으로 유용합니다.

```bash
python -m kr_image_uploader.audit --dir ..\data\raw\KR\details\20260609 --out ..\data\image_upload_failures.csv
```

### 옵션

- `--check-urls` 빠진 URL의 실제 상태코드를 GET으로 확인 (원인 분류용)
- `--retry-missing` 빠진 이미지만 다시 받아서 업로드 (기존 객체 무손상, 404 자동 스킵)
- `--out PATH` 빠진 이미지 목록을 CSV로 저장 (상태코드 포함)

## 테스트

```bash
# src/ 에서 실행
python -m unittest discover -s kr_image_uploader/tests -t .
```

성공하면 `Ran 15 tests ... OK` 만 출력됩니다.
