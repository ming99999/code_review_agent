from agents.review_agent import CodeReviewAgent
from agents import subagent


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

    assert result["summary"]["highlights"][:2] == [
        "총 인라인 코멘트: 1개",
        "Python lint: 1건",
    ]
    assert len(result["comments"]) == 1
    assert result["comments"][0]["file_path"] == "app/main.py"
    assert "unused import" in result["comments"][0]["body"]
