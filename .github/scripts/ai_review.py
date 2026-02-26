#!/usr/bin/env python3
import os, json, pathlib, subprocess, requests, sys

BASE   = os.getenv("PR_BASE_SHA")
HEAD   = os.getenv("PR_HEAD_SHA")
API    = os.getenv("CODE_REVIEW_API_URL")

# 1) changed files (Python, JavaScript, TypeScript, JSX, TSX, Vue)
try:
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", f"{BASE}..{HEAD}"], text=True
    )
except subprocess.CalledProcessError as e:
    print(f"::error ::Git diff failed: {e}")
    sys.exit(1)

# Support multiple language extensions
SUPPORTED_EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.vue'}
supported_files = [f for f in diff.splitlines() 
                   if any(f.endswith(ext) for ext in SUPPORTED_EXTENSIONS) 
                   and pathlib.Path(f).is_file()]

def set_output(name, value):
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"::set-output name={name}::{value}")

if not supported_files:
    # Actions 가 "has_files=false" 를 보고 early-exit
    set_output("has_files", "false")
    pathlib.Path("temp_pr_review.json").write_text("{}")
    sys.exit(0)

# 2) 각 파일의 diff 정보 수집
files_with_diff = []
for file_path in supported_files:
    try:
        # 파일의 전체 diff 정보 가져오기
        diff_content = subprocess.check_output(
            ["git", "diff", f"{BASE}..{HEAD}", "--", file_path], text=True
        )
        
        files_with_diff.append({
            "file_path": file_path,
            "code_content": pathlib.Path(file_path).read_text(encoding="utf-8"),
            "diff_content": diff_content
        })
    except Exception as e:
        print(f"::warning ::Failed to get diff for {file_path}: {e}")
        # diff 없이도 계속 진행
        files_with_diff.append({
            "file_path": file_path,
            "code_content": pathlib.Path(file_path).read_text(encoding="utf-8"),
            "diff_content": ""
        })

# 3) build payload
payload = {
    "files": files_with_diff,
    "model_name":  os.getenv("OPENAI_MODEL_NAME", "gpt-4o"),
    "review_style": "pr_markdown",
}

# 4) call AI API
try:
    resp = requests.post(f"{API}/review-pr", json=payload, timeout=300)
    if resp.status_code != 200:
        print(f"::error ::AI API failed {resp.status_code}: {resp.text}")
        sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"::error ::AI API request failed: {e}")
    sys.exit(1)

# 5) 저장 & flag
review_data = resp.json()
pathlib.Path("temp_pr_review.json").write_text(json.dumps(review_data, ensure_ascii=False, indent=2))
set_output("has_files", "true")
