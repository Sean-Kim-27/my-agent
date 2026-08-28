# Phase 5: 메모리 및 컨텍스트 관리 (Context Management) 구조 보강 필요

> 원본 수정 지시서 항목 #1. 권장 작업 우선순위 5순위.
> 전체 목록은 [README.md](./README.md) 참고.

---

### 1. 🧠 메모리 및 컨텍스트 관리 (Context Management) 구조 보강 필요

* **현재 상태:** `src/agent_framework/memory/in_memory.py`에 `max_messages` 기반 **개수(count) 트리밍**은 이미 구현되어 있음. 다만 **토큰 카운팅(token counting)** 기반 트리밍과 요약(summarization)을 위한 별도 인터페이스는 없음.
* **수정 지시:** 텍스트 요약 기능까지는 당장 구현하지 않더라도, 컨텍스트 윈도우가 가득 차기 전에 토큰 수 기준으로 오래된 메시지를 잘라내는 `ContextManager` 역할의 뼈대(Interface)를 `memory/` 하위에 신설할 것. `ConversationMemory`와 조합 가능한 구조로 설계.

---
