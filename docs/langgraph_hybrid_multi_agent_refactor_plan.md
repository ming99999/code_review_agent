# LangGraph 기반 Hybrid Multi-Agent 리팩토링 계획

## 1) 현재 구조 분석 (As-Is)

### 핵심 병목
- `CodeReviewAgent`가 단일 클래스에 분석/카테고리별 리뷰/최종 컴파일까지 모두 포함하고 있어 관심사 분리가 약함.
- 리뷰의 기본 단위가 파일 중심이며, PR 전체 관점(파일 간 상호작용) 분석이 구조적으로 1급 객체가 아님.
- 스타일/문법 계열 검출을 LLM+내장 analyzer가 함께 수행하여 라인 정밀도와 결정론적 재현성이 낮아질 여지가 있음.

### 재사용 가능한 자산
- `models/custom_openai.py`의 `CodeReviewChatOpenAI`: 멀티 에이전트 노드에서 공통 LLM 래퍼로 재사용 가능.
- `utils/diff_parser.py`의 `DiffParser`, `FileDiff`, `DiffHunk`: PR 전체 diff 파싱 및 라인 매핑에 즉시 활용 가능.
- `api/api_server.py`의 `/review-pr` 엔드포인트: 오케스트레이터 교체 시 API 호환성 유지 가능.

---

## 2) 목표 구조 (To-Be): 3-Tier `src/agents/`

요구하신 3개 파일로 역할을 분리합니다.

### A. `src/agents/state.py`
- `PRReviewState` (TypedDict)
- 병렬 노드 결과 집계를 위한 `Annotated[..., operator.add]` 사용
- 상태 스키마 예시
  - 입력: `pr_number`, `repo`, `files`, `full_diff`
  - 라우팅: `python_files`, `js_files`, `vue_files`
  - 도구 결과: `python_lints`, `js_lints`, `vue_lints`
  - LLM 결과: `python_comments`, `js_comments`, `vue_comments`
  - 횡단 분석: `cross_interaction_comments`
  - 최종: `overall_summary`, `inline_comments`, `final_output`

### B. `src/agents/subagent.py`
노드 비즈니스 로직을 모읍니다.

1. **State Initializer & Router 노드**
- 입력 파일 목록/확장자 기준 분류
- `DiffParser`로 full diff를 파싱해 파일별 변경 라인 인덱스 구성

2. **Linter Tool 노드 (결정론)**
- Python: Ruff JSON + 보안 스캔(pip-audit, gitleaks)
- JS/Vue: ESLint JSON (Vue는 필요 시 `vue-tsc` 진단 보강)
- 출력 정규화 스키마 통일:
  - `file_path`, `line`, `end_line`, `rule_id`, `severity`, `message`, `source`

3. **언어별 Expert Agent 노드 (추론)**
- 입력: 코드 + linter 결과 + 변경 라인 컨텍스트
- 출력: 인라인 코멘트(라인 번호 포함), 수정 예시 코드
- 노드 분리:
  - `python_expert_node`
  - `js_expert_node`
  - `vue_expert_node`

4. **Cross-Interaction Agent 노드**
- 입력: PR 전체 diff + 파일 메타
- 검출 예시:
  - FE 호출 경로/메서드 변경 vs BE 라우트 시그니처
  - API 응답 필드 변경 vs FE 소비 필드
  - 직렬화 포맷(JSON key) 불일치

5. **Supervisor 노드**
- 중복 코멘트 병합, severity 재정렬, 최종 summary 생성
- 출력 포맷을 기존 API 응답(`summary`, `comments`)과 호환

### C. `src/agents/review_agent.py`
- 그래프 Topology 정의 전용
- 노드 등록 + 엣지 연결 + fan-out/fan-in 구성
- `LangGraph` 오케스트레이터로서만 동작 (비즈니스 로직 제거)

---

## 3) `src/agents` 외 모듈 리팩토링 필요 사항 (권장)

결론: **다른 모듈도 일부 리팩토링하는 것이 목표 구조 달성에 유리**합니다. 단, 전면 재작성보다는 인터페이스/경계 정리에 집중합니다.

### A. `src/api/` (필수)
- `api_server.py`에서 `CodeReviewAgent` 직접 의존을 제거하고, 신규 `PRReviewOrchestrator`(LangGraph 엔트리)로 주입.
- `/review-pr` 요청 스키마를 PR 단위 컨텍스트(전체 diff, 파일 메타, optional base/head SHA) 중심으로 보강.
- backward compatibility를 위해 구 스키마 필드는 deprecate 경고 후 일정 기간 유지.

### B. `src/utils/` (필수)
- `diff_parser.py` 확장:
  - renamed/moved file 처리
  - file-level changed line index 캐시
  - hunk 기준 old/new line mapping 유틸 함수 노출
- 신규 `linter_runner.py`(또는 동등 유틸) 추가:
  - Ruff/ESLint/pip-audit/gitleaks 실행, timeout, 비정상 종료 코드 표준 처리
  - 결과를 공통 finding 스키마로 normalize

### C. `src/models/` (권장)
- `custom_openai.py`는 유지하되, 에이전트별 프롬프트 템플릿 주입을 위한 래퍼/팩토리 계층 추가.
- 토큰 사용량/지연시간/실패율을 노드 단위로 측정하기 위한 tracing hook 포인트 추가.

### D. 분석기 레거시 모듈 (`src/agents/*_analyzer.py`, `code_analyzer.py`) (권장)
- 즉시 삭제보다 **Phase-out 전략**:
  - 운영 API에서는 신규 orchestrator 단일 경로 유지
  - 레거시 분석기 모듈은 참조 제거 전까지 내부 호환용으로만 보존
  - 안정화 후 제거

### E. 설정/운영 (`requirements.txt`, 환경변수) (필수)
- Ruff/ESLint/pip-audit/gitleaks 의존성 및 실행 바이너리 경로를 명시.
- API 런타임 전환 플래그 없이 신규 파이프라인 단일 운영.

### F. 테스트 체계 (필수)
- 단위/통합 외에 회귀 테스트 추가:
  - 동일 PR 입력 대비 기준 스냅샷 결과 비교(코멘트 수, 라인 정합도)
  - 장애 주입 테스트(linter 미설치, timeout, 잘못된 JSON 출력)

---

## 4) 단계별 구현 계획 (Execution Plan)

### Step 1. 상태 모델/공통 스키마 도입
- `state.py` 생성
- Lint finding/inline comment/dataclass(or TypedDict) 공통화
- `operator.add` 병합 필드 명확화

### Step 2. Router + Diff 인덱싱 노드 구현
- `DiffParser` 재사용해 파일별 changed lines map 생성
- 확장자 라우팅(.py/.js/.jsx/.ts/.tsx/.vue)

### Step 3. Linter Tool 노드 구현
- subprocess 기반 JSON 실행기 유틸 추가(실패/타임아웃 처리 포함)
- Ruff/ESLint/pip-audit/gitleaks 결과를 공통 finding 스키마로 정규화
- 라인번호 매핑 정확도 검증 테스트 추가

### Step 4. 언어별 Expert LLM 노드 구현
- `CodeReviewChatOpenAI` 재사용
- 프롬프트 원칙
  - linter를 사실 소스로 사용
  - “이유 + 영향 + 수정 예시 코드 + 검증 포인트” 강제
  - 라인번호 없는 코멘트 금지

### Step 5. Cross-Interaction 노드 구현
- PR full diff에서 API contract 신호 추출
- FE/BE 페어링 휴리스틱(경로/함수명/DTO 키워드)
- 신뢰도(score)와 함께 코멘트 생성

### Step 6. Supervisor + 최종 출력 포맷 정리
- 중복/충돌 코멘트 정리
- `overall_summary`, `inline_comments` 생성
- 기존 `/review-pr` 응답과 호환성 유지

### Step 7. API 운영 경로 고정
- `api_server.py`에서 신규 orchestrator 단일 경로로 운영
- API 단에서는 legacy/hybrid 선택 옵션을 두지 않음
- 구 경로와의 비교는 오프라인 검증(테스트/리포트)으로만 수행

### Step 8. 테스트/검증
- 단위 테스트
  - diff 파싱-라인매핑
  - linter JSON 정규화
  - supervisor dedup
- 통합 테스트
  - 샘플 PR 입력 → summary/comments 스냅샷 검증
- 회귀/장애 테스트
  - linter 미설치/timeout/파싱오류 시 graceful degradation 검증

---

## 5) 권장 그래프 토폴로지 (LangGraph)

- `setup_router`
  - 분기: `python_linter`, `js_linter`, `vue_linter`
  - 병렬: `cross_interaction`
- `python_linter -> python_expert`
- `js_linter -> js_expert`
- `vue_linter -> vue_expert`
- `python_expert/js_expert/vue_expert/cross_interaction -> supervisor`
- `supervisor -> END`

조건부 엣지로 “해당 언어 파일 없으면 스킵” 처리.

---

## 6) 리스크 및 대응

- **리스크:** 실행 환경에 Ruff/ESLint/pip-audit/gitleaks 미설치
  - **대응:** 도구 부재 시 warning finding 생성 + LLM fallback 최소화
- **리스크:** large PR에서 토큰 과다
  - **대응:** 파일별 컨텍스트 클리핑 + 요약 캐시 + 중요도 우선순위
- **리스크:** FE-BE 연계 오탐
  - **대응:** confidence score + “확인 필요” 라벨
- **리스크:** 단일 경로 전환 시 초기 품질 이슈 발생 가능
  - **대응:** 통합/회귀 테스트와 샘플 PR 스냅샷 검증을 강화

---

## 7) 완료 기준 (Definition of Done)

### A. 아키텍처/기능
- 3-tier 파일 분리(`state.py`, `subagent.py`, `review_agent.py`) 완료
- Linter 결정론 결과가 인라인 라인 번호에 직접 연결됨
- 언어별 Expert + Cross-Interaction + Supervisor 노드가 PR 단위로 동작
- `/review-pr` 결과가 요약 + 인라인 코멘트 형태로 안정 출력

### B. 모듈 경계/운영
- `api_server.py`가 신규 orchestrator 단일 경로로 동작
- `utils`에 linter 실행/정규화 유틸과 diff line mapping 유틸이 분리되어 재사용 가능
- `models/custom_openai.py` 기반으로 에이전트별 prompt 주입과 노드 단위 tracing이 가능

### C. 품질 보증
- 기본 테스트(단위/통합) 통과
- 회귀 테스트(기준 스냅샷 대비 핵심 정합도) 통과
- 장애 테스트(linter 미설치/timeout/JSON 오류) 통과
