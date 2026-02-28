# Linter/Security Tool 설치 및 셋업 가이드

이 문서는 Hybrid Multi-Agent 파이프라인의 결정론적 품질/보안 도구를 실제 환경에서 실행하기 위한 설치 방법을 설명합니다.

적용 도구:
- 코드 품질: `ruff`, `eslint`
- 보안 점검: `pip-audit`, `gitleaks`

> 참고: 기존 `bandit`은 제거되었습니다.

## 1) 빠른 설치 (권장)

저장소 루트에서 아래 스크립트를 실행합니다.

```bash
bash scripts/setup_linters.sh
```

스크립트가 수행하는 작업:
1. Python 도구 설치 (`ruff`, `pip-audit`)
2. Node lint 도구 설치 (`eslint` + Vue/TS parser/plugin)
3. `gitleaks` 설치 시도(Conda 활성 환경이면 `$CONDA_PREFIX/bin` 우선 설치, 실패 시 로컬 바이너리 설치)
4. 설치 결과 버전 확인

## 2) 수동 설치

### Python 도구

```bash
python3 -m pip install --upgrade pip
python3 -m pip install ruff pip-audit
ruff --version
pip-audit --version
```

### Node lint 도구

```bash
npm install --save-dev eslint @eslint/js vue-eslint-parser eslint-plugin-vue @typescript-eslint/parser @typescript-eslint/eslint-plugin
./node_modules/.bin/eslint --version
```

### gitleaks

- 수동 설치 가이드: https://github.com/gitleaks/gitleaks
- 설치 후 확인:

```bash
gitleaks version
```

## 3) 런타임 동작 방식

`src/utils/linter_runner.py`는 다음 정책으로 동작합니다.
- 도구 미설치 시: 실패 대신 low-severity warning finding 생성
- 도구 실행 실패/JSON 파싱 실패 시: runner error finding 생성
- 정상 실행 시: 공통 finding 스키마로 normalize

보안 스캔 정책:
- `pip-audit`: Python 의존성 취약점 스캔 (`requirements.txt` 기준)
- `gitleaks`: 리포지토리 전체 secret 스캔 (`--no-git`, workspace source)

## 4) 운영 환경 권장사항

- CI 이미지에 `ruff`, `pip-audit`, `eslint`, `gitleaks` 사전 설치
- Node 버전은 LTS(18+ 권장)
- PR 검증 단계에서 보안 스캐너는 summary 섹션 우선 검토
- gitleaks false positive를 줄이기 위해 baseline/allowlist 정책 적용 고려

## 5) 트러블슈팅

### `gitleaks: command not found`
- `scripts/setup_linters.sh` 재실행
- Conda 환경 사용 시 `which gitleaks`가 `$CONDA_PREFIX/bin/gitleaks`를 가리키는지 확인
- PATH에 못 잡히는 경우 아래 중 하나를 사용:
  - `export GITLEAKS_BIN="$(pwd)/.local/bin/gitleaks"`
  - `export $(cat .env.tools | xargs)`  (setup 스크립트가 `.env.tools`를 생성한 경우)
- API 실행은 동일 셸에서 `PYTHONPATH=src python -m uvicorn api.api_server:app --host 0.0.0.0 --port 8000` 권장

### `pip-audit` 네트워크 오류
- 취약점 DB 조회 시 외부 네트워크가 필요할 수 있음
- CI에서 proxy/network 정책 확인

### lint 결과가 0건인데 코드 이슈가 있는 경우
- diff 기반 changed-lines 필터링으로 인해 변경 라인 외 이슈는 제외될 수 있음
- 전체 파일 분석이 필요하면 필터링 정책 조정 필요
