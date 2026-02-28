"""LangGraph orchestrator for PR-level hybrid multi-agent code review."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph

from .state import PRReviewState
from .subagent import (
    cross_interaction_node,
    js_expert_node,
    js_linter_node,
    python_expert_node,
    python_linter_node,
    setup_router_node,
    security_expert_node,
    security_scan_node,
    supervisor_node,
    vue_expert_node,
    vue_linter_node,
)

logger = logging.getLogger(__name__)


class CodeReviewAgent:
    """PR-level review agent backed by a hybrid LangGraph pipeline."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        review_style: str = "comprehensive",
        include_examples: bool = True,
    ):
        self.model_name = model_name
        self.review_style = review_style
        self.include_examples = include_examples
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(PRReviewState)

        workflow.add_node("setup_router", setup_router_node)
        workflow.add_node("python_linter", python_linter_node)
        workflow.add_node("js_linter", js_linter_node)
        workflow.add_node("vue_linter", vue_linter_node)
        workflow.add_node("python_expert", python_expert_node)
        workflow.add_node("js_expert", js_expert_node)
        workflow.add_node("vue_expert", vue_expert_node)
        workflow.add_node("cross_interaction", cross_interaction_node)
        workflow.add_node("security_scan", security_scan_node)
        workflow.add_node("security_expert", security_expert_node)
        workflow.add_node("supervisor", supervisor_node)

        workflow.set_entry_point("setup_router")

        workflow.add_edge("setup_router", "python_linter")
        workflow.add_edge("setup_router", "js_linter")
        workflow.add_edge("setup_router", "vue_linter")
        workflow.add_edge("setup_router", "cross_interaction")
        workflow.add_edge("setup_router", "security_scan")

        workflow.add_edge("python_linter", "python_expert")
        workflow.add_edge("js_linter", "js_expert")
        workflow.add_edge("vue_linter", "vue_expert")
        workflow.add_edge("security_scan", "security_expert")

        workflow.add_edge("python_expert", "supervisor")
        workflow.add_edge("js_expert", "supervisor")
        workflow.add_edge("vue_expert", "supervisor")
        workflow.add_edge("cross_interaction", "supervisor")
        workflow.add_edge("security_expert", "supervisor")

        workflow.add_edge("supervisor", END)

        return workflow.compile()

    def review_pr_files(self, files_data: List[Dict[str, str]]) -> Dict[str, Any]:
        """Run PR-level review and return API-compatible summary/comments."""

        full_diff = "\n".join([f.get("diff_content", "") for f in files_data if f.get("diff_content")])

        initial_state: PRReviewState = {
            "files": files_data,
            "full_diff": full_diff,
            "review_style": self.review_style,
            "python_lints": [],
            "js_lints": [],
            "vue_lints": [],
            "security_lints": [],
            "python_comments": [],
            "js_comments": [],
            "vue_comments": [],
            "security_comments": [],
            "cross_interaction_comments": [],
        }

        try:
            final_state = self.graph.invoke(initial_state)
            return {
                "summary": final_state.get("overall_summary", {}),
                "comments": final_state.get("inline_comments", []),
            }
        except Exception as exc:
            logger.error("PR review failed: %s", exc)
            return {
                "summary": {
                    "positive_feedback": f"리뷰 생성 실패: {exc}",
                    "highlights": [],
                    "top_priorities": [],
                    "growth_suggestions": [],
                },
                "comments": [],
            }

    def review_code(self, code_content: str, file_path: str, diff_content: str = "") -> str:
        """Backward-compatible single file wrapper that routes via PR flow."""

        result = self.review_pr_files(
            [
                {
                    "file_path": file_path,
                    "code_content": code_content,
                    "diff_content": diff_content,
                }
            ]
        )

        summary = result.get("summary", {})
        highlights = summary.get("highlights", [])
        comments = result.get("comments", [])

        lines = ["# PR Review (Single File Mode)"]
        for item in highlights:
            lines.append(f"- {item}")

        if comments:
            lines.append("\n## Inline Comments")
            for c in comments:
                lines.append(
                    f"- {c.get('file_path')}:{c.get('line_number')} [{c.get('severity')}] {c.get('body')}"
                )
        else:
            lines.append("\n- 인라인 코멘트가 없습니다.")

        return "\n".join(lines)
