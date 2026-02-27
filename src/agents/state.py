"""State definitions for PR-level hybrid multi-agent review graph."""

from __future__ import annotations

import operator
from typing import Any, Dict, List, TypedDict
from typing_extensions import Annotated


class LintFinding(TypedDict, total=False):
    """Normalized linter finding schema shared across tool nodes."""

    file_path: str
    line: int
    end_line: int
    rule_id: str
    severity: str
    message: str
    source: str


class InlineComment(TypedDict, total=False):
    """Inline review comment schema expected by API output."""

    file_path: str
    line_number: int
    body: str
    severity: str


class PRReviewState(TypedDict, total=False):
    """LangGraph state for PR-level review orchestration."""

    # Inputs
    files: List[Dict[str, str]]
    full_diff: str
    review_style: str

    # Routed file groups
    python_files: List[Dict[str, str]]
    js_files: List[Dict[str, str]]
    vue_files: List[Dict[str, str]]

    # Diff index
    changed_lines_by_file: Dict[str, List[int]]

    # Deterministic linter outputs
    python_lints: Annotated[List[LintFinding], operator.add]
    js_lints: Annotated[List[LintFinding], operator.add]
    vue_lints: Annotated[List[LintFinding], operator.add]
    security_lints: Annotated[List[LintFinding], operator.add]

    # LLM expert outputs
    python_comments: Annotated[List[InlineComment], operator.add]
    js_comments: Annotated[List[InlineComment], operator.add]
    vue_comments: Annotated[List[InlineComment], operator.add]
    security_comments: Annotated[List[InlineComment], operator.add]
    cross_interaction_comments: Annotated[List[InlineComment], operator.add]

    # Final output
    overall_summary: Dict[str, Any]
    inline_comments: List[InlineComment]
