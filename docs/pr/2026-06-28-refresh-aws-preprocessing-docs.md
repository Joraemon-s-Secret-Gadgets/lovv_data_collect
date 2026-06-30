## 변경사항

- 현재 AWS 조회 결과 기준으로 KR 전국 파이프라인 전처리 보고서를 갱신했습니다.
- `TourKoreaDomainDataV2` 조회 가이드에 라이브 카운트, S3 raw/image, S3 Vector 상태, Lambda 기본 테이블 주의사항을 추가했습니다.
- legacy `TourKoreaDomainData` 사용 문서와 오래된 전처리 보고서에 V2 기준/과거 기준을 명확히 표시했습니다.

## Notes

추후 복습을 통해서 code가 변경될 수 있습니다.
- `src/kr_details_pipeline/load.py`, `src/kr_details_pipeline/tests/test_load.py`의 기존 미커밋 변경은 이번 PR에 포함하지 않았습니다.
- 검증: `git diff --cached --check`.
- PR은 문서-only 변경입니다.
