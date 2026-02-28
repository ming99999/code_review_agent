from agents import subagent


def test_build_changed_line_index_from_diff():
    diff = """diff --git a/app/main.py b/app/main.py
@@ -1,2 +1,3 @@
 import os
+print('a')
+print('b')
"""
    index = subagent._build_changed_line_index(diff)
    assert "app/main.py" in index
    assert index["app/main.py"] == [2, 3]


def test_filter_findings_to_changed_lines():
    findings = [
        {"file_path": "app/main.py", "line": 2, "end_line": 2, "message": "keep"},
        {"file_path": "app/main.py", "line": 10, "end_line": 10, "message": "drop"},
    ]
    changed = {"app/main.py": [2, 3]}
    filtered = subagent._filter_findings_to_changed_lines(findings, changed)
    assert len(filtered) == 1
    assert filtered[0]["message"] == "keep"


def test_security_scan_node_uses_pip_audit_and_gitleaks(monkeypatch):
    monkeypatch.setattr(subagent, "run_pip_audit", lambda: [{"file_path": "requirements.txt", "line": 1, "end_line": 1, "rule_id": "PYSEC", "severity": "high", "message": "dep vuln", "source": "pip-audit"}])
    monkeypatch.setattr(subagent, "run_gitleaks", lambda: [{"file_path": "web/app.js", "line": 4, "end_line": 4, "rule_id": "secret", "severity": "high", "message": "secret found", "source": "gitleaks"}])

    state = {"files": [], "full_diff": ""}
    out = subagent.security_scan_node(state)
    assert "security_lints" in out
    assert len(out["security_lints"]) == 2


def test_supervisor_includes_security_comments():
    state = {
        "python_comments": [],
        "js_comments": [],
        "vue_comments": [],
        "cross_interaction_comments": [],
        "security_comments": [
            {"file_path": "requirements.txt", "line_number": 1, "severity": "high", "body": "[pip-audit] vuln"}
        ],
        "python_lints": [],
        "js_lints": [],
        "vue_lints": [],
        "security_lints": [{"source": "pip-audit"}],
    }

    result = subagent.supervisor_node(state)
    assert "overall_summary" in result
    assert "inline_comments" in result
    assert len(result["inline_comments"]) == 1
    assert set(result["overall_summary"].keys()) >= {
        "positive_feedback",
        "highlights",
        "top_priorities",
        "growth_suggestions",
    }
    assert isinstance(result["overall_summary"]["highlights"], list)


def test_supervisor_prioritizes_security_and_high_severity():
    state = {
        "python_comments": [
            {"file_path": "a.py", "line_number": 10, "severity": "medium", "body": "[ruff] style"}
        ],
        "js_comments": [],
        "vue_comments": [],
        "cross_interaction_comments": [
            {"file_path": "PR", "line_number": 1, "severity": "medium", "body": "🌐 FE-BE 상호작용 점검"}
        ],
        "security_comments": [
            {"file_path": "requirements.txt", "line_number": 1, "severity": "high", "body": "[pip-audit] vuln"}
        ],
        "python_lints": [],
        "js_lints": [],
        "vue_lints": [],
        "security_lints": [{"source": "pip-audit"}],
    }

    result = subagent.supervisor_node(state)
    comments = result["inline_comments"]
    assert comments[0]["severity"] == "high"
    assert "pip-audit" in comments[0]["body"]
    assert isinstance(result["overall_summary"]["top_priorities"], list)
