# Phase 4: Phase 5 실행 안전장치 (Execution Safety) 보강

> 원본 수정 지시서 항목 #3. 권장 작업 우선순위 4순위 (설정 관리).
> 전체 목록은 [README.md](./README.md) 참고.

---

### 3. 🚨 Phase 5 실행 안전장치 (Execution Safety) 보강

* **현재 상태:** `agent.py`에 `max_steps` 초과 시 예외를 발생시키는 루프 가드는 **이미 구현되어 있음** (`agent.py:159, 279`). `ToolExecutor`에도 `default_timeout=30s` 타임아웃이 **이미 구현되어 있음** (`tools/executor.py:24, 86`). 다만 **`max_retries`(재시도) 로직은 전무**하며, 이 설정값들이 `config/settings.py`의 `Settings`가 아닌 각 클래스 생성자 kwarg로 흩어져 있어 중앙 관리가 안 됨.
* **수정 지시:** `config/settings.py`에 `AgentConfig` 모델(`max_steps`, `tool_timeout`, `max_retries` 필드 포함)을 신설하여 실행 안전장치 설정을 한 곳에서 관리할 것. `max_steps`/`timeout` 로직 자체는 이미 있으므로 **삭제·재작성 금지, 설정 중앙화만 수행**.

---
