#!/usr/bin/env python3
"""Scan tracked source and docs for obvious credential patterns."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    "agenticapi",
    "tests",
    "docs",
    "configs",
    "scripts",
    "README.md",
    "pyproject.toml",
    ".env.example",
]
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|secret|token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
]
ALLOW = ("your-key", "your_api_key", "change-me", "replace-me", "redacted", "fake-key")


def iter_files() -> list[Path]:
    files: list[Path] = []
    for name in TARGETS:
        path = ROOT / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file()
                and ".venv" not in item.parts
                and "__pycache__" not in item.parts
            )
    return files


def main() -> int:
    findings: list[str] = []
    for path in iter_files():
        if path.suffix not in {".py", ".md", ".json", ".toml", ".sh", ".example", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(token in line.lower() for token in ALLOW):
                continue
            for pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{number}: {pattern.pattern}")
                    break
    if findings:
        print("potential secrets found:")
        for finding in findings:
            print(finding)
        return 1
    print("no credential-like strings found in scanned files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
