#!/usr/bin/env python3
"""Secrets hygiene scanner — a fast first-pass check for common leaks.

Scans a repo for: hardcoded credentials, weak hashes, direct secret comparisons,
tracked .env files, and missing .gitignore entries. Not a replacement for
gitleaks/bandit, but catches the classics before they ship.

Usage: python secrets_scan.py [repo_root]
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Patterns that look like secrets (heuristic, not exhaustive)
SECRET_PATTERNS = [
    (
        r'(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[:=]\s*[\'"]?[\w\-.]{16,}[\'"]?',
        "suspected hardcoded credential",
    ),
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI-style API key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"eyJ[a-zA-Z0-9\-_]+\.eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+", "JWT token"),
    (r"-----BEGIN (?:RSA|EC|OPENSSH|DSA) PRIVATE KEY-----", "private key"),
]

WEAK_HASH_PATTERNS = [
    (r"hashlib\.(md5|sha1)\(", "weak hash (md5/sha1)"),
    (r"(?:==|!=)\s*(?:password|passwd|secret|token)", "direct comparison of secret"),
]


def check_gitignore(repo_root: Path) -> list[str]:
    issues = []
    gi = repo_root / ".gitignore"
    if not gi.exists():
        issues.append("ERROR: No .gitignore found")
        return issues
    content = gi.read_text()
    for entry in [".env", "*.pem", "*.key", "*.keystore", "credentials.json"]:
        if entry not in content:
            issues.append(f"WARNING: .gitignore missing '{entry}'")
    return issues


def scan_file(path: Path) -> list[str]:
    issues = []
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return issues

    for pattern, desc in SECRET_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line_no = text[: m.start()].count("\n") + 1
            snippet = m.group()[:60]
            issues.append(f"  {path}:{line_no} [{desc}] {snippet}")

    for pattern, desc in WEAK_HASH_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line_no = text[: m.start()].count("\n") + 1
            issues.append(f"  {path}:{line_no} [{desc}]")

    return issues


def main() -> None:
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"Scanning: {repo_root}\n")

    all_issues: list[str] = []

    # 1. .gitignore check
    all_issues.extend(check_gitignore(repo_root))

    # 2. Check if .env is tracked
    result = os.popen(f"cd {repo_root} && git ls-files --error-unmatch .env 2>&1").read()
    if "error" not in result:
        all_issues.append("CRITICAL: .env is tracked by git!")

    # 3. Scan source files
    scan_exts = {".py", ".js", ".ts", ".sh", ".yaml", ".yml", ".toml", ".json", ".env"}
    for path in repo_root.rglob("*"):
        if path.suffix in scan_exts and ".git" not in path.parts:
            if path.name in (".env", "credentials.json"):
                all_issues.append(f"CRITICAL: Sensitive file in repo: {path}")
            all_issues.extend(scan_file(path))

    if all_issues:
        print(f"Found {len(all_issues)} issue(s):\n")
        for issue in all_issues:
            print(issue)
        sys.exit(1)
    else:
        print("No issues found.")


if __name__ == "__main__":
    main()
