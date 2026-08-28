# Phase 7: Human-in-the-Loop 승인 게이트 부재

> 원본 수정 지시서 항목 #9. 권장 작업 우선순위 7순위.
> 전체 목록은 [README.md](./README.md) 참고.

---

### 9. ✋ Human-in-the-Loop 승인 게이트 부재 (신규)

* **현재 상태:** `ToolDefinition`/`ToolExecutor` 어디에도 "확인이 필요한 툴"이라는 개념이 없음. 등록된 툴은 파괴적 동작(파일 삭제, 외부 API 쓰기 등)이어도 사용자 확인 없이 즉시 실행됨.
* **수정 지시:** `models/tool.py`의 `ToolDefinition`에 `requires_confirmation: bool = False` 필드를 추가하고, `ToolExecutor.execute()` 실행 전 해당 플래그가 True인 경우 `AgentCallbackHandler`를 통해 승인 콜백을 거치도록 훅을 추가할 것. CLI/Discord/Telegram 각 어댑터에서 이 콜백을 구현하여 최종 승인 UX를 제공.

---
