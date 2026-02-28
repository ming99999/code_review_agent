# code_review_agent

LangGraph 기반 PR 코드리뷰 오케스트레이터와 결정론적 린터/보안 스캐너를 결합한 코드 리뷰 에이전트입니다.

## 어떻게 테스트하면 되나? (권장 검증 순서)

### 1) 자동 테스트 전체 실행

- ✅ `PYTHONPATH=src pytest -q`
- 유닛/통합 테스트를 한 번에 확인합니다.
- 현재 커버:
  - 도구 미설치/타임아웃/JSON 오류
  - diff 라인 필터링
  - cross-interaction 신호
  - supervisor 우선순위/요약 출력
  - `review_pr_files` 응답 shape

### 2) 정적 컴파일 체크

- ✅ `python -m compileall src tests`
- 기본 문법/임포트 문제를 빠르게 잡습니다.

### 3) 도구 설치/환경 체크

- ✅ `bash scripts/setup_linters.sh`
- `ruff`, `pip-audit`, `eslint`, `gitleaks` 설치/버전 확인을 자동 수행합니다.
- 설치 정책/트러블슈팅은 `docs/linter_setup.md`를 확인하세요.

### 4) API 실제 동작 스모크 테스트

서버 실행:

- ✅ `PYTHONPATH=src python -m uvicorn api.api_server:app --host 0.0.0.0 --port 8000`
- `python -m` 방식은 현재 활성화된 conda/env 인터프리터를 확실히 사용하기 때문에 환경 불일치 문제를 줄여줍니다.

헬스체크:

- ✅ `curl -s http://localhost:8000/health`

PR 리뷰 스모크(예시 payload):

- ✅ `curl -s -X POST http://localhost:8000/review-pr -H 'Content-Type: application/json' -d '{"files":[{"file_path":"app/main.py","code_content":"import os\nprint(\"ok\")\n","diff_content":"diff --git a/app/main.py b/app/main.py\n@@ -0,0 +1,2 @@\n+import os\n+print(\"ok\")\n"}]}'`
- 응답에 `summary`, `comments`, `status`가 나오면 기본 플로우 정상입니다.
