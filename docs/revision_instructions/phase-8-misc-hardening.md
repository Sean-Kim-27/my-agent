# Phase 8: 나머지 보강 (Provider 중립적 툴 콜링 검증 / eval 기반 계산기 툴)

> 원본 수정 지시서 항목 #4, #10. 권장 작업 우선순위 8순위.
> 전체 목록은 [README.md](./README.md) 참고.

---

### 4. 🛠️ Provider 중립적 툴 콜링 (Provider-neutral Tool Calling) 검증

> ⚠️ **이미 대부분 구현되어 있음.** 원 지시서의 "명확하지 않은 상태"라는 진단은 부정확함.

* **현재 상태:** `llm/openai_compatible.py:223-238`와 `llm/anthropic_provider.py:239-251`에서 각 Provider가 raw JSON 응답을 공통 `ToolCall` 모델(`models/tool.py`)로 이미 정규화하여 반환하고 있음. 다만 `llm/base.py`에는 이 정규화를 강제하는 **추상 메서드가 없어서**, 새 Provider 추가 시 컨벤션에만 의존하는 구조.
* **수정 지시:** 기존 정규화 로직은 그대로 유지하고, `llm/base.py`의 `LLMProvider`에 `_parse_tool_calls(raw: Any) -> list[ToolCall]` 같은 추상 메서드를 추가하여 향후 Provider 추가 시 정규화를 컴파일 타임에 강제할 것.

---

### 10. 🧮 `main.py`의 `eval()` 기반 계산기 툴 (신규, 보안)

* **현재 상태:** `main.py`의 `calculate` 툴이 `eval(expression, {"__builtins__": None}, {})`을 사용 중. 현재는 문자 화이트리스트(`0-9+-*/(). %`)로 방어되어 있어 즉각적인 위험은 낮으나, `eval` 기반 패턴 자체가 향후 화이트리스트가 느슨해지면 바로 RCE로 이어질 수 있는 코드 냄새임.
* **수정 지시:** `eval()` 대신 `ast.literal_eval` + 직접 파싱, 또는 `numexpr`/`asteval` 같은 안전한 수식 평가 라이브러리로 교체할 것.

---
