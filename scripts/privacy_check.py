from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "__pycache__", "workspace", "dist", "build"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".yml", ".yaml", ".txt", ".gitignore"}
PATTERNS = {
    "OpenAI-style API key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"gh[opsu]_[A-Za-z0-9]{20,}"),
    "Windows user path": re.compile(r"[A-Za-z]:\\Users\\(?!Example(?:\\|$))[^\\\s]+", re.I),
    "likely personal email": re.compile(r"\b(?!alex@example\.invalid)[A-Z0-9._%+-]+@(?!example\.invalid\b)[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "Chinese mobile number": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
}


def main() -> int:
    findings = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS or part.startswith(".venv") for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitignore":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append("%s: %s (%s)" % (path.relative_to(ROOT), label, match.group(0)[:80]))
    if findings:
        print("Privacy scan failed:")
        print("\n".join("- " + item for item in findings))
        return 1
    print("PASS: no configured secret or personal-data patterns found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
