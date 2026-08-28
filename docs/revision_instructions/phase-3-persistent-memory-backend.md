# Phase 3: 영속 메모리 백엔드 부재

> 원본 수정 지시서 항목 #7. 권장 작업 우선순위 3순위 (실서비스 배포 전제조건).
> 전체 목록은 [README.md](./README.md) 참고.

---

### 7. 💾 영속 메모리 백엔드 부재 (신규)

* **현재 상태:** `ConversationMemory` 추상 인터페이스(`memory/base.py`)는 잘 설계되어 있으나, 실제 구현체는 `InMemoryConversationMemory` 단 하나뿐임. 프로세스가 재시작되면 모든 대화 세션이 소실됨 — Discord/Telegram 봇을 실서비스로 운영할 경우 가장 치명적인 제약.
* **수정 지시:** 최소 1개의 영속 백엔드(Redis 또는 SQLite)를 `memory/` 하위에 추가 구현할 것. `SessionManager`의 `memory_factory` 주입 구조는 이미 되어 있으므로 (`memory/session.py:20`), 새 구현체만 `ConversationMemory`를 상속하면 별도 코어 수정 없이 교체 가능함.

---
