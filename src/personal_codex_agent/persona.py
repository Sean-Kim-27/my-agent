from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaMode:
    name: str
    description: str
    instruction: str


MODES: dict[str, PersonaMode] = {
    "default": PersonaMode(
        name="default",
        description="기본 개인 비서 모드",
        instruction="너는 사용자의 개인 Codex 에이전트다. 요청을 정확히 수행하고 검증된 결과를 간결하게 보고한다.",
    ),
    "dev": PersonaMode(
        name="dev",
        description="소프트웨어 개발 모드",
        instruction="소프트웨어 개발 모드로 동작한다. 변경 전 테스트를 작성하고, 구현 후 테스트와 컴파일 검증을 우선한다.",
    ),
    "research": PersonaMode(
        name="research",
        description="리서치 모드",
        instruction="리서치 모드로 동작한다. 확인 가능한 근거를 우선하고, 불확실한 내용은 명확히 표시한다.",
    ),
}


def resolve_mode(name: str | None) -> PersonaMode:
    if not name:
        return MODES["default"]
    return MODES.get(name.strip().lower(), MODES["default"])


def list_modes() -> list[str]:
    return list(MODES)


def build_prompt(mode: str | None, user_prompt: str) -> str:
    persona = resolve_mode(mode)
    return f"[mode: {persona.name}]\n{persona.instruction}\n\n사용자 요청:\n{user_prompt}"
