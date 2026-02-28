"""Utilities for running deterministic linters/security scanners and normalizing results."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List


LintFinding = Dict[str, Any]


def run_ruff(file_path: str, code_content: str, timeout_sec: int = 20) -> List[LintFinding]:
    """Run Ruff on stdin content and normalize JSON output."""
    if not shutil.which("ruff"):
        return [_tool_unavailable_finding(file_path, "ruff")]

    cmd = ["ruff", "check", "--output-format", "json", "-"]
    try:
        result = subprocess.run(
            cmd,
            input=code_content,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [_runner_error_finding(file_path, "ruff", f"timeout after {timeout_sec}s")]

    if result.returncode not in (0, 1):
        return [_runner_error_finding(file_path, "ruff", result.stderr or result.stdout)]

    findings: List[LintFinding] = []
    try:
        for item in json.loads(result.stdout or "[]"):
            findings.append(
                {
                    "file_path": file_path,
                    "line": int(item.get("location", {}).get("row", 1)),
                    "end_line": int(item.get("end_location", {}).get("row", item.get("location", {}).get("row", 1))),
                    "rule_id": item.get("code", "ruff"),
                    "severity": "medium",
                    "message": item.get("message", "Ruff finding"),
                    "source": "ruff",
                }
            )
    except json.JSONDecodeError:
        return [_runner_error_finding(file_path, "ruff", "Invalid JSON output")]

    return findings


def run_eslint(file_path: str, code_content: str, timeout_sec: int = 20) -> List[LintFinding]:
    """Run ESLint on stdin content and normalize JSON output."""
    if not shutil.which("eslint"):
        return [_tool_unavailable_finding(file_path, "eslint")]

    cmd = ["eslint", "--stdin", "--stdin-filename", file_path, "--format", "json"]
    default_config = "src/agents/eslint.config.js"
    if os.path.exists(default_config):
        cmd.extend(["--config", default_config])

    try:
        result = subprocess.run(
            cmd,
            input=code_content,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [_runner_error_finding(file_path, "eslint", f"timeout after {timeout_sec}s")]

    if result.returncode not in (0, 1):
        return [_runner_error_finding(file_path, "eslint", result.stderr or result.stdout)]

    findings: List[LintFinding] = []
    try:
        data = json.loads(result.stdout or "[]")
        for file_result in data:
            for msg in file_result.get("messages", []):
                severity = "high" if int(msg.get("severity", 1)) == 2 else "medium"
                findings.append(
                    {
                        "file_path": file_path,
                        "line": int(msg.get("line", 1)),
                        "end_line": int(msg.get("endLine", msg.get("line", 1))),
                        "rule_id": msg.get("ruleId") or "eslint",
                        "severity": severity,
                        "message": msg.get("message", "ESLint finding"),
                        "source": "eslint",
                    }
                )
    except json.JSONDecodeError:
        return [_runner_error_finding(file_path, "eslint", "Invalid JSON output")]

    return findings


def run_pip_audit(requirements_path: str = "requirements.txt", timeout_sec: int = 60) -> List[LintFinding]:
    """Run pip-audit for dependency vulnerabilities and normalize output."""
    if not shutil.which("pip-audit"):
        return [_tool_unavailable_finding("requirements.txt", "pip-audit")]

    if not os.path.exists(requirements_path):
        return []

    cmd = ["pip-audit", "-r", requirements_path, "-f", "json"]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_sec, check=False)
    except subprocess.TimeoutExpired:
        return [_runner_error_finding(requirements_path, "pip-audit", f"timeout after {timeout_sec}s")]

    if result.returncode not in (0, 1):
        return [_runner_error_finding(requirements_path, "pip-audit", result.stderr or result.stdout)]

    findings: List[LintFinding] = []
    try:
        payload = json.loads(result.stdout or "[]")
        for dep in payload.get("dependencies", []):
            for vul in dep.get("vulns", []):
                findings.append(
                    {
                        "file_path": requirements_path,
                        "line": 1,
                        "end_line": 1,
                        "rule_id": vul.get("id", "pip-audit"),
                        "severity": "high",
                        "message": f"{dep.get('name')} {dep.get('version')} vulnerable: {vul.get('description', '')[:200]}",
                        "source": "pip-audit",
                    }
                )
    except (json.JSONDecodeError, AttributeError):
        return [_runner_error_finding(requirements_path, "pip-audit", "Invalid JSON output")]

    return findings


def run_gitleaks(scan_path: str = ".", timeout_sec: int = 60) -> List[LintFinding]:
    """Run gitleaks secret scanning and normalize output."""
    gitleaks_bin = _resolve_gitleaks_bin()
    if not gitleaks_bin:
        return [_tool_unavailable_finding("PR", "gitleaks")]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        report_path = tmp.name

    try:
        cmd = [
            gitleaks_bin,
            "detect",
            "--no-git",
            "--source",
            scan_path,
            "--report-format",
            "json",
            "--report-path",
            report_path,
        ]
        try:
            result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_sec, check=False)
        except subprocess.TimeoutExpired:
            return [_runner_error_finding("PR", "gitleaks", f"timeout after {timeout_sec}s")]

        # gitleaks returns non-zero when leaks are found; treat 1 as success-with-findings.
        if result.returncode not in (0, 1):
            return [_runner_error_finding("PR", "gitleaks", result.stderr or result.stdout)]

        findings: List[LintFinding] = []
        try:
            data = json.loads(open(report_path, "r", encoding="utf-8").read() or "[]")
            for item in data:
                findings.append(
                    {
                        "file_path": item.get("File", "PR"),
                        "line": int(item.get("StartLine", 1)),
                        "end_line": int(item.get("EndLine", item.get("StartLine", 1))),
                        "rule_id": item.get("RuleID", "gitleaks"),
                        "severity": "high",
                        "message": f"Potential secret detected ({item.get('Description', 'gitleaks')})",
                        "source": "gitleaks",
                    }
                )
        except (json.JSONDecodeError, OSError, ValueError):
            return [_runner_error_finding("PR", "gitleaks", "Invalid JSON output")]

        return findings
    finally:
        try:
            os.remove(report_path)
        except OSError:
            pass


def _resolve_gitleaks_bin() -> str | None:
    """Resolve gitleaks executable from env, PATH, or project-local install path."""
    explicit = os.getenv("GITLEAKS_BIN")
    if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
        return explicit

    in_path = shutil.which("gitleaks")
    if in_path:
        return in_path

    project_root = Path(__file__).resolve().parents[2]
    local_bin = project_root / ".local" / "bin" / "gitleaks"
    if local_bin.is_file() and os.access(local_bin, os.X_OK):
        return str(local_bin)

    return None


def _tool_unavailable_finding(file_path: str, tool: str) -> LintFinding:
    return {
        "file_path": file_path,
        "line": 1,
        "end_line": 1,
        "rule_id": f"{tool}_not_installed",
        "severity": "low",
        "message": f"{tool} is not installed in runtime environment.",
        "source": tool,
    }


def _runner_error_finding(file_path: str, tool: str, detail: str) -> LintFinding:
    return {
        "file_path": file_path,
        "line": 1,
        "end_line": 1,
        "rule_id": f"{tool}_runner_error",
        "severity": "medium",
        "message": f"{tool} execution failed: {detail[:300]}",
        "source": tool,
    }
