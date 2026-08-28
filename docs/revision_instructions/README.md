# 수정 지시서 (통합본) — 페이즈 분할

> 기존 5개 항목 + 코드베이스 재검증 결과 및 추가 발견 5개 항목을 통합한 최종본입니다.
> ⚠️ 표시된 항목은 검증 결과 이미 구현되어 있어 지시 내용이 최신화 필요함을 의미합니다.

원본 `revision_instructions.md`의 내용을 변경 없이 "권장 작업 우선순위" 순서에 따라 페이즈별 파일로 분할했습니다. 각 파일의 본문은 원본 항목 텍스트를 그대로 유지합니다.

---

## 권장 작업 우선순위 (페이즈 목록)

1. [Phase 1: CLI 어댑터 분리 (아키텍처 일관성)](./phase-1-cli-adapter-independence.md) — 원본 항목 #2
2. [Phase 2: LLM 재시도/백오프 (안정성)](./phase-2-llm-retry-backoff.md) — 원본 항목 #6
3. [Phase 3: 영속 메모리 백엔드 최소 1개 (실서비스 배포 전제조건)](./phase-3-persistent-memory-backend.md) — 원본 항목 #7
4. [Phase 4: `AgentConfig` 중앙화 (설정 관리)](./phase-4-agent-config-centralization.md) — 원본 항목 #3
5. [Phase 5: 토큰 기반 컨텍스트 트리밍](./phase-5-token-based-context-trimming.md) — 원본 항목 #1
6. [Phase 6: CI 파이프라인](./phase-6-ci-pipeline.md) — 원본 항목 #8
7. [Phase 7: Human-in-the-Loop 게이트](./phase-7-human-in-the-loop-gate.md) — 원본 항목 #9
8. [Phase 8: 나머지 보강 (Provider 중립적 툴 콜링 검증 / eval 기반 계산기 툴 개선)](./phase-8-misc-hardening.md) — 원본 항목 #4, #10
9. [Phase 9: 작업 불필요 (완료됨) — 로깅 보안 시크릿 마스킹](./phase-9-logging-secret-masking.md) — 원본 항목 #5

---

## 원본 우선순위 텍스트 (그대로 보존)

1. **#2** CLI 어댑터 분리 (아키텍처 일관성)
2. **#6** LLM 재시도/백오프 (안정성)
3. **#7** 영속 메모리 백엔드 최소 1개 (실서비스 배포 전제조건)
4. **#3** `AgentConfig` 중앙화 (설정 관리)
5. **#1** 토큰 기반 컨텍스트 트리밍
6. **#8** CI 파이프라인
7. **#9** Human-in-the-Loop 게이트
8. **#4, #10** 나머지 보강
9. **#5** 작업 불필요 (완료됨)
