# -*- coding: utf-8 -*-
"""Rewrite plugin repository branding to this fork after upstream reset.

Keeps third-party CDN assets (SXP-Simon/profile_assets) and this script intact.
Does not rewrite auto-sync workflow upstream remote.
Does NOT change plugin version / astrbot_version - those always stay from upstream.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORK_OWNER = "muqing-kg"
FORK_REPO = "astrbot_plugin_qq_group_daily_analysis"
FORK_SLUG = f"{FORK_OWNER}/{FORK_REPO}"
FORK_URL = f"https://github.com/{FORK_SLUG}"

TEXT_REPLACEMENTS: list[tuple[str, str]] = [
    ("https://github.com/SXP-Simon/astrbot-qq-group-daily-analysis", FORK_URL),
    ("https://github.com/SXP-Simon/astrbot_plugin_qq_group_daily_analysis", FORK_URL),
    ("https://deepwiki.com/SXP-Simon/astrbot_plugin_qq_group_daily_analysis", FORK_URL),
    ("gh/SXP-Simon/astrbot_plugin_qq_group_daily_analysis", f"gh/{FORK_SLUG}"),
    ("repo=SXP-Simon/astrbot_plugin_qq_group_daily_analysis", f"repo={FORK_SLUG}"),
    ("SXP-Simon / astrbot_plugin_qq_group_daily_analysis", f"{FORK_OWNER} / {FORK_REPO}"),
    ("SXP-Simon/astrbot_plugin_qq_group_daily_analysis", FORK_SLUG),
]

SKIP_DIR_NAMES = {".git", ".venv", "venv", "__pycache__", "node_modules", "backups", "previews", "profile_assets"}
SKIP_FILE_NAMES = {"CHANGELOG.md", "apply_fork_branding.py"}
SKIP_REL_PATHS = {
    Path(".github/workflows/auto-sync-upstream.yml"),
    Path("WECHATBRIDGE.md"),
    Path("scripts/apply_fork_branding.py"),
    Path("scripts/apply_wechat_avatar_patch.py"),
    Path("scripts/apply_soft_glass_template.py"),
}
TEXT_SUFFIXES = {".md", ".yml", ".yaml", ".json", ".html", ".htm", ".py", ".txt", ".css", ".js", ".ts"}
VERSION_LINE_RE = re.compile(r"^(?P<indent>\s*)version\s*:\s*.*$", re.M)
ASTRBOT_VERSION_LINE_RE = re.compile(r"^(?P<indent>\s*)astrbot_version\s*:\s*.*$", re.M)


def _should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if rel in SKIP_REL_PATHS:
        return True
    if set(rel.parts) & SKIP_DIR_NAMES:
        return True
    if path.name in SKIP_FILE_NAMES:
        return True
    if "profile_assets" in rel.as_posix():
        return True
    return False


def _rewrite_text(text: str) -> str:
    out = text
    for old, new in TEXT_REPLACEMENTS:
        out = out.replace(old, new)
    return out


def _extract_version_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, pattern in (("version", VERSION_LINE_RE), ("astrbot_version", ASTRBOT_VERSION_LINE_RE)):
        m = pattern.search(text)
        if m:
            fields[key] = m.group(0)
    return fields


def _restore_version_fields(text: str, original_fields: dict[str, str]) -> str:
    out = text
    for key, pattern in (("version", VERSION_LINE_RE), ("astrbot_version", ASTRBOT_VERSION_LINE_RE)):
        if key not in original_fields:
            continue
        if pattern.search(out):
            out = pattern.sub(original_fields[key], out, count=1)
    return out


def _rewrite_metadata(path: Path) -> bool:
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8")
    original_versions = _extract_version_fields(original)
    lines: list[str] = []
    for line in original.splitlines(keepends=True):
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("version:") or stripped.startswith("astrbot_version:"):
            lines.append(line)
            continue
        if stripped.startswith("author:"):
            lines.append(f"{indent}author: {FORK_OWNER} # \u4f5c\u8005\n")
            continue
        if stripped.startswith("repo:"):
            lines.append(f"{indent}repo: {FORK_URL} # \u63d2\u4ef6\u7684\u4ed3\u5e93\u5730\u5740\n")
            continue
        lines.append(line)
    text = _restore_version_fields(_rewrite_text("".join(lines)), original_versions)
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def apply() -> int:
    changed_files: list[str] = []
    meta = ROOT / "metadata.yaml"
    if _rewrite_metadata(meta):
        changed_files.append(str(meta.relative_to(ROOT)).replace("\\", "/"))
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == meta.resolve():
            continue
        if _should_skip(path):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", "Dockerfile"}:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = _rewrite_text(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8", newline="\n")
            changed_files.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    if meta.exists():
        current = meta.read_text(encoding="utf-8")
        m = VERSION_LINE_RE.search(current)
        am = ASTRBOT_VERSION_LINE_RE.search(current)
        print("version policy: keep upstream values only")
        if m:
            print(" ", m.group(0).strip())
        if am:
            print(" ", am.group(0).strip())
    print(f"FORK branding -> {FORK_SLUG}")
    print(f"changed files: {len(changed_files)}")
    for rel in changed_files[:50]:
        print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(apply())
