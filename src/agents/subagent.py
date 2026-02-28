"""Sub-agent nodes for the PR-level hybrid multi-agent review graph."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

from models.custom_openai import CodeReviewChatOpenAI
from utils.diff_parser import DiffParser
from utils.linter_runner import run_eslint, run_gitleaks, run_pip_audit, run_ruff
from .state import InlineComment, LintFinding, PRReviewState

logger = logging.getLogger(__name__)

_PROMPTS: Dict[str, Any] = {}
try:
    _PROMPT_PATH = Path(__file__).resolve().parents[1] / "models" / "prompts.yml"
    if _PROMPT_PATH.exists():
        _PROMPTS = yaml.safe_load(_PROMPT_PATH.read_text(encoding="utf-8")) or {}
except Exception as exc:
    logger.warning("Failed to load prompts.yml: %s", exc)


def setup_router_node(state: PRReviewState) -> PRReviewState:
    """Initialize state and route files by language."""
    files = state.get("files", [])
    diff_content = state.get("full_diff", "")

    python_files: List[Dict[str, str]] = []
    js_files: List[Dict[str, str]] = []
    vue_files: List[Dict[str, str]] = []

    for file_data in files:
        file_path = file_data.get("file_path", "")
        lower_path = file_path.lower()
        if lower_path.endswith(".py"):
            python_files.append(file_data)
        elif lower_path.endswith(".vue"):
            vue_files.append(file_data)
        elif lower_path.endswith((".js", ".jsx", ".ts", ".tsx")):
            js_files.append(file_data)

    return {
        "python_files": python_files,
        "js_files": js_files,
        "vue_files": vue_files,
        "changed_lines_by_file": _build_changed_line_index(diff_content),
    }


def python_linter_node(state: PRReviewState) -> PRReviewState:
    findings: List[LintFinding] = []
    for file_data in state.get("python_files", []):
        findings.extend(run_ruff(file_data.get("file_path", ""), file_data.get("code_content", "")))
    return {"python_lints": findings}


def js_linter_node(state: PRReviewState) -> PRReviewState:
    findings: List[LintFinding] = []
    for file_data in state.get("js_files", []):
        findings.extend(run_eslint(file_data.get("file_path", ""), file_data.get("code_content", "")))
    return {"js_lints": findings}


def vue_linter_node(state: PRReviewState) -> PRReviewState:
    findings: List[LintFinding] = []
    for file_data in state.get("vue_files", []):
        findings.extend(run_eslint(file_data.get("file_path", ""), file_data.get("code_content", "")))
    return {"vue_lints": findings}


def security_scan_node(state: PRReviewState) -> PRReviewState:
    """Run repository-level security scanners (pip-audit + gitleaks)."""
    findings: List[LintFinding] = []
    findings.extend(run_pip_audit())
    findings.extend(run_gitleaks())
    return {"security_lints": findings}


def python_expert_node(state: PRReviewState) -> PRReviewState:
    return {"python_comments": _expert_comments_for_language(state, "python")}


def js_expert_node(state: PRReviewState) -> PRReviewState:
    return {"js_comments": _expert_comments_for_language(state, "javascript")}


def vue_expert_node(state: PRReviewState) -> PRReviewState:
    return {"vue_comments": _expert_comments_for_language(state, "vue")}


def security_expert_node(state: PRReviewState) -> PRReviewState:
    """Convert security findings to actionable inline comments."""
    return {"security_comments": _findings_to_inline_comments(state.get("security_lints", []))}


def cross_interaction_node(state: PRReviewState) -> PRReviewState:
    """Find minimal cross-file API interaction risks from full PR diff."""
    full_diff = state.get("full_diff", "")
    comments: List[InlineComment] = []

    api_route_changes = re.findall(
        r"\+\s*@(?:app|router)\.(get|post|put|delete)\(['\"]([^'\"]+)",
        full_diff,
    )
    frontend_fetches = re.findall(
        r"\+.*(?:fetch|axios\.(?:get|post|put|delete))\(['\"]([^'\"]+)",
        full_diff,
    )

    changed_routes = {_normalize_route(route) for _, route in api_route_changes}
    if changed_routes:
        for path in frontend_fetches:
            normalized_path = _normalize_route(path)
            if normalized_path.startswith("/") and normalized_path not in changed_routes:
                changed_route_text = ", ".join(sorted(changed_routes))
                comments.append(
                    {
                        "file_path": "PR",
                        "line_number": 1,
                        "severity": "medium",
                        "body": (
                            f"🌐 FE-BE 상호작용 점검: 프론트 호출 경로 `{normalized_path}` "
                            f"가 백엔드 변경 라우트({changed_route_text})와 불일치할 수 있습니다."
                        ),
                    }
                )

    # method-level minimal signal when axios method is explicitly changed
    changed_backend_methods = {method.lower() for method, _ in api_route_changes}
    changed_frontend_methods = {
        method.lower()
        for method in re.findall(r"\+.*axios\.(get|post|put|delete)\(", full_diff)
    }
    missing_methods = changed_frontend_methods - changed_backend_methods
    if missing_methods and changed_backend_methods:
        missing_text = ", ".join(sorted(missing_methods))
        backend_text = ", ".join(sorted(changed_backend_methods))
        comments.append(
            {
                "file_path": "PR",
                "line_number": 1,
                "severity": "medium",
                "body": (
                    "🌐 FE-BE 메서드 점검(중간): 프론트에서 변경된 HTTP 메서드 "
                    f"`{missing_text}` 가 백엔드 변경 메서드({backend_text})와 다를 수 있습니다."
                ),
            }
        )

    return {"cross_interaction_comments": comments}


def supervisor_node(state: PRReviewState) -> PRReviewState:
    merged: List[InlineComment] = []
    merged.extend(state.get("python_comments", []))
    merged.extend(state.get("js_comments", []))
    merged.extend(state.get("vue_comments", []))
    merged.extend(state.get("security_comments", []))
    merged.extend(state.get("cross_interaction_comments", []))
    deduped = _dedupe_comments(merged)
    prioritized = _prioritize_comments(deduped)

    summary = _generate_summary_with_llm(state, prioritized)
    if not summary:
        grouped = _group_comments_by_source(prioritized)
        summary = {
            "positive_feedback": "좋은 시도를 많이 해주셨습니다. 다음 개선 포인트를 반영하면 코드 품질이 더 빠르게 성장할 수 있어요.",
            "highlights": [
                f"총 인라인 코멘트: {len(prioritized)}개",
                f"Python lint: {len(state.get('python_lints', []))}건",
                f"JS lint: {len(state.get('js_lints', []))}건",
                f"Vue lint: {len(state.get('vue_lints', []))}건",
                f"Security scan: {len(state.get('security_lints', []))}건",
                f"보안 관련 코멘트: {len(grouped.get('security', []))}개",
                f"상호작용 관련 코멘트: {len(grouped.get('cross', []))}개",
            ],
            "top_priorities": [c["body"][:120] for c in prioritized[:3]],
            "growth_suggestions": ["중요 이슈부터 순서대로 해결하며 리팩토링 근거(Why)를 기록해보세요."],
        }

    return {"overall_summary": summary, "inline_comments": prioritized}


def _expert_comments_for_language(state: PRReviewState, language: str) -> List[InlineComment]:
    if language == "python":
        files = state.get("python_files", [])
        findings = state.get("python_lints", [])
        prompt_key = "comprehensive"
    elif language == "vue":
        files = state.get("vue_files", [])
        findings = state.get("vue_lints", [])
        prompt_key = "vue_comprehensive"
    else:
        files = state.get("js_files", [])
        findings = state.get("js_lints", [])
        prompt_key = "javascript_comprehensive"

    if not files or not findings:
        return []

    filtered_findings = _filter_findings_to_changed_lines(findings, state.get("changed_lines_by_file", {}))
    if not filtered_findings:
        return []

    if os.getenv("OPENAI_API_KEY"):
        try:
            llm = CodeReviewChatOpenAI(model_name=os.getenv("OPENAI_MODEL_NAME", "gpt-4o"), temperature=0.1)
            return _llm_generate_comments(llm, prompt_key, files, filtered_findings)
        except Exception as exc:
            logger.warning("LLM expert node failed for %s: %s", language, exc)

    return _findings_to_inline_comments(filtered_findings)


def _llm_generate_comments(
    llm: CodeReviewChatOpenAI,
    prompt_key: str,
    files: List[Dict[str, str]],
    findings: List[LintFinding],
) -> List[InlineComment]:
    base_prompt = _get_review_prompt(prompt_key)
    system_content = (
        f"{base_prompt}\n\n"
        "아래 지시를 반드시 따르세요:\n"
        "- Linter findings에 없는 문제를 추측으로 만들지 마세요(환각 금지).\n"
        "- 사실 근거는 반드시 findings 또는 제공된 code excerpt에서만 인용하세요.\n"
        "- 응답은 JSON 배열만 반환하세요. 각 항목은 file_path, line_number, severity, body를 포함하세요.\n"
        "- body에는 반드시 '칭찬 한 줄 + Why + 개선 제안'이 포함되어야 합니다.\n"
        "- line_number는 정수여야 하며 비어있으면 안 됩니다."
    )

    file_excerpts = []
    for item in files:
        file_excerpts.append(
            {
                "file_path": item.get("file_path", ""),
                "code_excerpt": (item.get("code_content", "")[:600]),
            }
        )

    response = llm.invoke(
        [
            SystemMessage(content=system_content),
            HumanMessage(content=json.dumps({"files": file_excerpts[:20], "findings": findings[:30]}, ensure_ascii=False)),
        ]
    )

    payload = response.content if hasattr(response, "content") else "[]"
    data = _safe_json_load(payload)
    if not isinstance(data, list):
        return _findings_to_inline_comments(findings)

    comments: List[InlineComment] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path", "")).strip()
        line_number = item.get("line_number")
        if not file_path or not isinstance(line_number, int):
            continue
        comments.append(
            {
                "file_path": file_path,
                "line_number": line_number,
                "severity": str(item.get("severity", "medium")),
                "body": str(item.get("body", "좋은 시도입니다. Why와 함께 개선안을 제안합니다.")),
            }
        )

    return comments if comments else _findings_to_inline_comments(findings)


def _generate_summary_with_llm(state: PRReviewState, comments: List[InlineComment]) -> Dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        return {}

    try:
        llm = CodeReviewChatOpenAI(model_name=os.getenv("OPENAI_MODEL_NAME", "gpt-4o"), temperature=0.1)
        prompt = _get_review_prompt("pr_summary")
        system_content = (
            f"{prompt}\n\n"
            "추가 지시:\n"
            "- 시니어 멘토가 주니어에게 전하는 긍정적/격려 톤을 유지하세요.\n"
            "- 취약점/개선점은 성장 포인트로 표현하세요.\n"
            "- 사실은 comments와 lint counts에서만 추출하세요(환각 금지).\n"
            "- JSON 객체만 반환하세요."
        )
        response = llm.invoke(
            [
                SystemMessage(content=system_content),
                HumanMessage(
                    content=json.dumps(
                        {
                            "lint_counts": {
                                "python": len(state.get("python_lints", [])),
                                "js": len(state.get("js_lints", [])),
                                "vue": len(state.get("vue_lints", [])),
                                "security": len(state.get("security_lints", [])),
                            },
                            "comments": comments[:20],
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        parsed = _safe_json_load(response.content if hasattr(response, "content") else "{}")
        if isinstance(parsed, dict) and parsed.get("positive_feedback"):
            return parsed
    except Exception as exc:
        logger.warning("summary llm generation failed: %s", exc)

    return {}


def _findings_to_inline_comments(findings: List[LintFinding]) -> List[InlineComment]:
    comments: List[InlineComment] = []
    for finding in findings:
        comments.append(
            {
                "file_path": finding.get("file_path", ""),
                "line_number": int(finding.get("line", 1) or 1),
                "severity": finding.get("severity", "medium"),
                "body": (
                    f"[칭찬] 좋은 시도입니다. [{finding.get('source', 'linter')}] {finding.get('message', '이슈 확인 필요')} "
                    f"(rule: {finding.get('rule_id', 'N/A')}) / Why: 안정성과 유지보수성을 높일 수 있어요."
                ),
            }
        )
    return comments


def _build_changed_line_index(diff_content: str) -> Dict[str, List[int]]:
    if not diff_content:
        return {}

    parser = DiffParser()
    file_diffs = parser.parse_diff(diff_content)

    index: Dict[str, List[int]] = defaultdict(list)
    for file_diff in file_diffs:
        for hunk in file_diff.hunks:
            for line_no, _ in hunk.additions:
                index[file_diff.new_path].append(line_no)

    return {k: sorted(set(v)) for k, v in index.items()}


def _filter_findings_to_changed_lines(
    findings: List[LintFinding],
    changed_lines_by_file: Dict[str, List[int]],
) -> List[LintFinding]:
    if not changed_lines_by_file:
        return findings

    filtered: List[LintFinding] = []
    for finding in findings:
        file_path = finding.get("file_path", "")
        changed_lines = set(changed_lines_by_file.get(file_path, []))
        if not changed_lines:
            continue
        line = int(finding.get("line", 1) or 1)
        end_line = int(finding.get("end_line", line) or line)
        if any(current_line in changed_lines for current_line in range(line, end_line + 1)):
            filtered.append(finding)
    return filtered


def _dedupe_comments(comments: List[InlineComment]) -> List[InlineComment]:
    seen = set()
    deduped: List[InlineComment] = []
    for comment in comments:
        key = (comment.get("file_path", ""), comment.get("line_number", 1), comment.get("body", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(comment)
    return deduped


def _prioritize_comments(comments: List[InlineComment]) -> List[InlineComment]:
    """Sort comments by severity then source priority for actionable ordering."""

    severity_weight = {"high": 0, "critical": 0, "medium": 1, "low": 2}

    def _source_bucket(comment: InlineComment) -> int:
        body = str(comment.get("body", "")).lower()
        if "pip-audit" in body or "gitleaks" in body:
            return 0
        if "fe-be" in body or "상호작용" in body or "메서드 점검" in body:
            return 1
        return 2

    return sorted(
        comments,
        key=lambda c: (
            severity_weight.get(str(c.get("severity", "medium")).lower(), 1),
            _source_bucket(c),
            str(c.get("file_path", "")),
            int(c.get("line_number", 1) or 1),
        ),
    )


def _group_comments_by_source(comments: List[InlineComment]) -> Dict[str, List[InlineComment]]:
    grouped: Dict[str, List[InlineComment]] = {"security": [], "cross": [], "lint": []}
    for comment in comments:
        body = str(comment.get("body", "")).lower()
        if "pip-audit" in body or "gitleaks" in body:
            grouped["security"].append(comment)
        elif "fe-be" in body or "상호작용" in body or "메서드 점검" in body:
            grouped["cross"].append(comment)
        else:
            grouped["lint"].append(comment)
    return grouped


def _get_review_prompt(style_key: str) -> str:
    review_styles = _PROMPTS.get("review_styles", {}) if isinstance(_PROMPTS, dict) else {}
    style = review_styles.get(style_key, {}) if isinstance(review_styles, dict) else {}
    return style.get("system_prompt", "당신은 시니어 멘토 코드리뷰어입니다. 한국어로 작성하세요.")


def _safe_json_load(payload: str) -> Any:
    text = (payload or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}


def _normalize_route(path: str) -> str:
    """Normalize route for lightweight FE/BE route comparison."""
    normalized = (path or "").strip()
    if not normalized:
        return normalized
    # remove query string and trailing slash (except root)
    normalized = normalized.split("?", 1)[0]
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized
