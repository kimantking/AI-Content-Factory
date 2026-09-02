#!/usr/bin/env python3
"""Fail the build if a real secret looks committed.

Usage:  python scripts/security/scan_secrets.py [path]
Exit 0 = clean, exit 1 = findings.

An allowlist lives in scripts/security/secret_allowlist.txt (one substring per
line). Keep it tight — it is for known-safe placeholders only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
ALLOWLIST_FILE = Path(__file__).with_name("secret_allowlist.txt")

_SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", ".venv", "venv",
              "__pycache__", ".pytest_cache", "storage", "outputs", "backups",
              ".ruff_cache", ".mypy_cache", "coverage"}
_SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".wav",
                ".mp3", ".pdf", ".ico", ".woff", ".woff2", ".ttf", ".lock", ".dump",
                ".tar", ".gz", ".zip"}

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{40,}")),
    ("google_oauth_token", re.compile(r"ya29\.[A-Za-z0-9_\-]{50,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("private_key_block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("fernet_key_literal", re.compile(r"(ACF_MASTER_KEY|SECRET_KEY)\s*[:=]\s*['\"][A-Za-z0-9_\-]{30,}=*['\"]")),
    ("dsn_with_password", re.compile(r"postgres(?:ql)?://[^\s:'\"]+:[^\s:'\"@/]{6,}@[^\s/'\"]+")),
    ("aws_secret", re.compile(r"aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+]{40}['\"]?", re.I)),
    ("bearer_literal", re.compile(r"Authorization['\"]?\s*[:=]\s*['\"]Bearer\s+[A-Za-z0-9._\-]{20,}['\"]")),
]

# obvious placeholders that must never count
_PLACEHOLDER = re.compile(r"(example|changeme|placeholder|your[_-]?key|xxx+|dummy|test[_-]?secret|"
                          r"mock|REDACTED|<[^>]+>|\$\{[^}]+\})", re.I)


def _allowlist() -> list[str]:
    if ALLOWLIST_FILE.exists():
        return [ln.strip() for ln in ALLOWLIST_FILE.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
    return []


def scan(root: Path) -> list[dict]:
    allow = _allowlist()
    findings: list[dict] = []
    for p in root.rglob("*"):
        if p.is_dir() or any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in _SKIP_SUFFIX:
            continue
        if p.name == "scan_secrets.py" or p.name == "secret_allowlist.txt":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if len(line) > 4000:
                continue
            for name, pat in PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                snippet = m.group(0)
                if _PLACEHOLDER.search(line) or any(a in line for a in allow):
                    continue
                preview = snippet[:16].encode("ascii", "replace").decode("ascii")
                findings.append({"rule": name, "file": str(p.relative_to(root)),
                                 "line": lineno, "match": preview + "..."})
    return findings


def main() -> int:
    findings = scan(ROOT)
    if not findings:
        print(f"scan_secrets: clean ({ROOT})")
        return 0
    print(f"scan_secrets: {len(findings)} finding(s):")
    for f in findings:
        print(f"  [{f['rule']}] {f['file']}:{f['line']}  {f['match']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
