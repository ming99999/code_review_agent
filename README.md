# code_review_agent

LangGraph 기반 PR 코드 리뷰 오케스트레이터입니다. 단일 파일 중심 리뷰를 넘어, PR 단위에서 결정론적 린터/보안 스캔 결과와 LLM 리뷰를 결합해 **재현 가능한 코드 리뷰**를 제공하는 것을 목표로 합니다.

## 프로젝트 요약

### 목표
- PR 단위 코드 변경을 언어/보안 관점에서 일관되게 검토
- LLM 단독 추론 의존도를 낮추고, 린터/보안 도구 기반의 사실(fact) 중심 리뷰 강화
- API 서버에서 즉시 호출 가능한 `summary + inline comments` 형태의 결과 제공

### 방향성
- **Deterministic first**: Ruff/ESLint/pip-audit/gitleaks 결과를 공통 스키마로 정규화
- **Hybrid multi-agent**: LangGraph로 라우팅/언어별 전문가/보안/슈퍼바이저를 분리
- **운영 재현성**: setup 스크립트와 문서로 환경 차이를 줄이고, conda 기반 실행 경로를 명확화

## 프로젝트 구조

```text
src/
  agents/
    review_agent.py      # LangGraph 오케스트레이터 엔트리
    subagent.py          # 라우터/린터/전문가/보안/슈퍼바이저 노드
    state.py             # PRReviewState, finding/comment 스키마
  api/
    api_server.py        # FastAPI 엔드포인트 (/health, /review, /review-pr)
  models/
    prompts.yml          # LLM 시스템 프롬프트/스타일 설정
  utils/
    linter_runner.py     # Ruff/ESLint/pip-audit/gitleaks 실행/정규화
scripts/
  setup_linters.sh       # 린터/보안 도구 설치 스크립트

docs/
  linter_setup.md        # 도구 설치/운영/트러블슈팅
  langgraph_hybrid_multi_agent_refactor_plan.md

tests/
  test_linter_runner_security.py
  test_subagent_pipeline.py
  test_review_agent_integration.py
```

## 사용 방법

### 1) 의존성 설치
```bash
python -m pip install -r requirements.txt
```

### 2) 린터/보안 도구 설치
```bash
bash scripts/setup_linters.sh
```
- conda 환경이 활성화되어 있으면 gitleaks를 `$CONDA_PREFIX/bin`에 우선 설치합니다.
- PATH 이슈가 있으면 `docs/linter_setup.md`의 `GITLEAKS_BIN`/`.env.tools` 가이드를 참고하세요.

### 3) API 실행
```bash
PYTHONPATH=src python -m uvicorn api.api_server:app --host 0.0.0.0 --port 8000
```
- `python -m` 방식으로 현재 활성 인터프리터(conda/env)를 강제해 실행 환경 불일치를 줄입니다.

### 4) API 호출 예시
헬스체크:
```bash
curl -s http://localhost:8000/health
```

PR 리뷰:
```bash
curl -s -X POST http://localhost:8000/review-pr \
  -H 'Content-Type: application/json' \
  -d '{"files":[{"file_path":"app/main.py","code_content":"import os\nprint(\"ok\")\n","diff_content":"diff --git a/app/main.py b/app/main.py\n@@ -0,0 +1,2 @@\n+import os\n+print(\"ok\")\n"}]}'
```

## 테스트 방법 (권장 검증 순서)

### 1) 자동 테스트 전체 실행
- ✅ `PYTHONPATH=src pytest -q`
- 커버 범위:
  - 도구 미설치/타임아웃/JSON 오류
  - diff 라인 필터링
  - cross-interaction 신호
  - supervisor 우선순위/요약
  - `review_pr_files` 응답 shape

### 2) 정적 컴파일 체크
- ✅ `python -m compileall src tests`
- 문법/임포트 문제를 빠르게 확인

### 3) 도구 설치/환경 체크
- ✅ `bash scripts/setup_linters.sh`
- `ruff`, `pip-audit`, `eslint`, `gitleaks` 설치/버전 확인

### 4) API 스모크 테스트
- ✅ `curl -s http://localhost:8000/health`
- ✅ `/review-pr` 호출 후 응답에 `summary`, `comments`, `status` 포함 여부 확인
