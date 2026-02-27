from utils import linter_runner
import subprocess


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_pip_audit_tool_unavailable(monkeypatch):
    monkeypatch.setattr(linter_runner.shutil, "which", lambda _: None)
    findings = linter_runner.run_pip_audit()
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "pip-audit_not_installed"


def test_run_gitleaks_tool_unavailable(monkeypatch):
    monkeypatch.setattr(linter_runner.shutil, "which", lambda _: None)
    findings = linter_runner.run_gitleaks()
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "gitleaks_not_installed"


def test_run_pip_audit_timeout(monkeypatch):
    monkeypatch.setattr(linter_runner.shutil, "which", lambda _: "/usr/bin/pip-audit")
    monkeypatch.setattr(linter_runner.os.path, "exists", lambda _: True)

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="pip-audit", timeout=1)

    monkeypatch.setattr(linter_runner.subprocess, "run", _raise_timeout)
    findings = linter_runner.run_pip_audit(timeout_sec=1)
    assert findings[0]["rule_id"] == "pip-audit_runner_error"
    assert "timeout" in findings[0]["message"]


def test_run_gitleaks_invalid_json_report(monkeypatch):
    monkeypatch.setattr(linter_runner.shutil, "which", lambda _: "/usr/bin/gitleaks")
    monkeypatch.setattr(linter_runner.subprocess, "run", lambda *_a, **_k: _FakeResult(returncode=0, stdout="", stderr=""))

    # force invalid JSON read
    monkeypatch.setattr(linter_runner, "open", lambda *_a, **_k: type("_X", (), {"read": lambda self: "{"})(), raising=False)
    findings = linter_runner.run_gitleaks()
    assert findings[0]["rule_id"] == "gitleaks_runner_error"
