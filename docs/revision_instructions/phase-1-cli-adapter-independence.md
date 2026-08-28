# Phase 1: CLI 어댑터 독립성 확보

> 원본 수정 지시서 항목 #2. 권장 작업 우선순위 1순위 (아키텍처 일관성).
> 전체 목록은 [README.md](./README.md) 참고.

---

### 2. 🔌 CLI 어댑터 독립성 확보

* **현재 상태:** Discord/Telegram 연동 코드는 `integrations/discord/`, `integrations/telegram/`로 잘 분리되어 있으나, `src/agent_framework/main.py`에는 `input()`/`print()` 기반 터미널 I/O와 슬래시 커맨드 파싱, Agent 호출 로직이 전부 뒤섞여 있음 (실측 확인됨 — 의존성 역전 원칙 위반).
* **수정 지시:** `integrations/cli/` 폴더를 신설하여 라우터 모듈을 분리할 것. `main.py`는 설정을 읽고 CLI/Discord/Telegram 어댑터 중 하나를 실행 유도하는 진입점 역할에만 충실하도록 리팩터링.

---
