from agents.review_agent import CodeReviewAgent
from agents import subagent
from types import SimpleNamespace


def test_review_pr_files_returns_api_compatible_shape(monkeypatch):
    monkeypatch.setattr(subagent, "run_ruff", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(subagent, "run_eslint", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(subagent, "run_pip_audit", lambda: [])
    monkeypatch.setattr(subagent, "run_gitleaks", lambda: [])

    agent = CodeReviewAgent()
    result = agent.review_pr_files(
        [
            {
                "file_path": "app/main.py",
                "code_content": "print('ok')\n",
                "diff_content": "diff --git a/app/main.py b/app/main.py\n@@ -0,0 +1,1 @@\n+print('ok')\n",
            }
        ]
    )

    assert isinstance(result, dict)
    assert "summary" in result
    assert "comments" in result
    assert set(result["summary"].keys()) >= {
        "positive_feedback",
        "highlights",
        "top_priorities",
        "growth_suggestions",
    }


def test_cross_interaction_route_and_method_signals():
    diff = """diff --git a/web/app.js b/web/app.js
@@ -1,2 +1,3 @@
+axios.post('/api/v1/users')
+fetch('/api/v2/users/')
 diff --git a/api/routes.py b/api/routes.py
@@ -1,3 +1,4 @@
+@router.get('/api/v1/users')
"""
    out = subagent.cross_interaction_node({"full_diff": diff})
    comments = out["cross_interaction_comments"]

    # route mismatch should be detected (/api/v2/users vs /api/v1/users)
    assert any("/api/v2/users" in c["body"] for c in comments)
    # method mismatch signal should also be present (post vs get)
    assert any("메서드 점검" in c["body"] for c in comments)


def test_review_pr_files_snapshot_like_regression(monkeypatch):
    monkeypatch.setattr(
        subagent,
        "run_ruff",
        lambda *_a, **_k: [
            {
                "file_path": "app/main.py",
                "line": 2,
                "end_line": 2,
                "rule_id": "F401",
                "severity": "medium",
                "message": "unused import",
                "source": "ruff",
            }
        ],
    )
    monkeypatch.setattr(subagent, "run_eslint", lambda *_a, **_k: [])
    monkeypatch.setattr(subagent, "run_pip_audit", lambda: [])
    monkeypatch.setattr(subagent, "run_gitleaks", lambda: [])

    agent = CodeReviewAgent()
    result = agent.review_pr_files(
        [
            {
                "file_path": "app/main.py",
                "code_content": "import os\nprint('ok')\n",
                "diff_content": "diff --git a/app/main.py b/app/main.py\n@@ -0,0 +1,2 @@\n+import os\n+print('ok')\n",
            }
        ]
    )

    # LLM summary can vary by runtime env, so verify schema/format instead of exact text.
    assert set(result["summary"].keys()) >= {
        "positive_feedback",
        "highlights",
        "top_priorities",
        "growth_suggestions",
    }
    assert isinstance(result["summary"]["highlights"], list)
    assert isinstance(result["summary"]["top_priorities"], list)
    assert len(result["comments"]) == 1
    comment = result["comments"][0]
    assert set(comment.keys()) >= {"file_path", "line_number", "severity", "body"}
    assert comment["file_path"] == "app/main.py"
    assert isinstance(comment["line_number"], int)
    assert comment["severity"] in {"low", "medium", "high", "critical"}
    assert isinstance(comment["body"], str)
    assert comment["body"].strip()


def test_llm_comment_response_validates_required_fields():
    class FakeLLM:
        def invoke(self, _messages):
            return SimpleNamespace(
                content='[{"file_path":"app/main.py","line_number":2,"severity":"medium","body":"칭찬 + Why + 개선 제안"}]'
            )

    out = subagent._llm_generate_comments(
        llm=FakeLLM(),
        prompt_key="comprehensive",
        files=[{"file_path": "app/main.py", "code_content": "import os\nprint('ok')\n"}],
        findings=[{"file_path": "app/main.py", "line": 2, "severity": "medium", "message": "unused import", "source": "ruff"}],
    )

    assert len(out) == 1
    assert set(out[0].keys()) >= {"file_path", "line_number", "severity", "body"}
    assert isinstance(out[0]["line_number"], int)


def test_llm_comment_response_invalid_json_falls_back_to_findings():
    class FakeLLM:
        def invoke(self, _messages):
            return SimpleNamespace(content="not-json")

    out = subagent._llm_generate_comments(
        llm=FakeLLM(),
        prompt_key="comprehensive",
        files=[{"file_path": "app/main.py", "code_content": "import os\nprint('ok')\n"}],
        findings=[{"file_path": "app/main.py", "line": 2, "severity": "medium", "message": "unused import", "source": "ruff"}],
    )

    assert len(out) == 1
    assert out[0]["file_path"] == "app/main.py"
    assert out[0]["line_number"] == 2
