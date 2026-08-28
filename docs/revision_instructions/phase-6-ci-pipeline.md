# Phase 6: CI/CD 파이프라인 부재

> 원본 수정 지시서 항목 #8. 권장 작업 우선순위 6순위.
> 전체 목록은 [README.md](./README.md) 참고.

---

### 8. ⚙️ CI/CD 파이프라인 부재 (신규)

* **현재 상태:** `.github/workflows` 디렉터리가 존재하지 않음. `pytest`/`mypy --strict`/`ruff`가 로컬에서만 실행되고 있어, PR 병합 시점에 품질 게이트가 없음.
* **수정 지시:** GitHub Actions 워크플로우를 추가하여 push/PR 시 `pytest`, `mypy --strict`, `ruff check`를 자동 실행하도록 구성할 것. 현재 67개 테스트가 모두 mock 기반이라 실행 속도가 매우 빠르므로 (0.5초대) CI 비용 부담은 낮음.

---
