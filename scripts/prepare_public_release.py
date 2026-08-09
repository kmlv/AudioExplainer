#!/usr/bin/env python3
"""Create and audit an allowlisted source tree for public release."""

from __future__ import annotations

import argparse
import posixpath
import re
import shutil
import sys
from pathlib import Path


PUBLIC_FILES = (
    ".github/workflows/ci.yml",
    ".gitignore",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "pyproject.toml",
    "scripts/prepare_public_release.py",
    "share/templates/discovery/agy-rules.md",
    "share/templates/discovery/audio-first-contract.md",
    "share/templates/discovery/claude-skill/SKILL.md",
    "share/templates/discovery/codex-skill/SKILL.md",
    "src/audioexplainer/__init__.py",
    "src/audioexplainer/cli.py",
    "src/audioexplainer/dialogue.py",
    "src/audioexplainer/doctor.py",
    "src/audioexplainer/engine.py",
    "src/audioexplainer/library.py",
    "src/audioexplainer/math_content.py",
    "src/audioexplainer/player.py",
    "src/audioexplainer/preprocess.py",
    "src/audioexplainer/providers.py",
    "src/audioexplainer/safety.py",
    "src/audioexplainer/voices.py",
    "tests/test_cli_contract.py",
    "tests/test_doctor.py",
    "tests/test_player_library.py",
    "tests/test_public_release.py",
    "tests/test_timing.py",
    "uv.lock",
)
REQUIRED_FILES = set(PUBLIC_FILES)


def collect_public_files(root: Path) -> list[Path]:
    """Return regular, allowlisted files relative to *root*."""
    files: list[Path] = []
    for name in PUBLIC_FILES:
        path = root / name
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in the public export: {name}")
        if path.is_file():
            files.append(path)
    return sorted(set(files))


def _text_issues(path: Path, relative: str) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return [
            f"{relative}: binary or non-UTF-8 files require an explicit public allowlist entry"
        ]

    issues: list[str] = []
    forbidden_literals = [
        ("/" + "Users/", "absolute macOS user path", set()),
        ("/" + "home/", "absolute Linux user path", set()),
        ("session" + "_id", "session metadata", set()),
    ]
    for needle, label, allowed_files in forbidden_literals:
        if relative in allowed_files:
            continue
        if needle in text:
            issues.append(f"{relative}: contains {label}")

    maintainer_name = "Krist" + "ian"
    if maintainer_name in text and relative not in {"LICENSE", "pyproject.toml"}:
        issues.append(f"{relative}: contains a personal name outside attribution files")

    secret_patterns = {
        "private key": re.compile("BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY"),
        "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b"),
        "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    }
    for label, pattern in secret_patterns.items():
        if pattern.search(text):
            issues.append(f"{relative}: resembles a {label}")
    return issues


def audit_public_files(root: Path, files: list[Path] | None = None) -> list[str]:
    """Return audit failures for an allowlisted source tree."""
    files = collect_public_files(root) if files is None else files
    relative_names = {path.relative_to(root).as_posix() for path in files}
    issues = [f"missing required file: {name}" for name in sorted(REQUIRED_FILES - relative_names)]
    for path in files:
        relative = path.relative_to(root).as_posix()
        issues.extend(_text_issues(path, relative))
    issues.extend(_markdown_link_issues(root, files))
    return issues


def _markdown_link_issues(root: Path, files: list[Path]) -> list[str]:
    """Reject relative Markdown links whose targets are absent from the export."""
    relative_names = {path.relative_to(root).as_posix() for path in files}
    issues: list[str] = []
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.strip().split("#", 1)[0].split("?", 1)[0]
            if not target or target.startswith("#") or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                continue
            if target.startswith("/"):
                issues.append(f"{relative}: absolute Markdown link is not public-safe: {target}")
                continue
            normalized = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
            if normalized.startswith("../") or normalized not in relative_names:
                issues.append(f"{relative}: Markdown link target is not exported: {target}")
    return issues


def export_public_tree(source: Path, destination: Path) -> int:
    """Copy the allowlisted source set to a new destination and return file count."""
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    files = collect_public_files(source)
    issues = audit_public_files(source, files)
    if issues:
        raise ValueError("public source audit failed:\n- " + "\n- ".join(issues))

    destination.mkdir(parents=True)
    for path in files:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    exported = collect_public_files(destination)
    issues = audit_public_files(destination, exported)
    if issues:
        raise ValueError("export audit failed:\n- " + "\n- ".join(issues))
    return len(exported)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new directory for the clean export")
    parser.add_argument("--check-only", action="store_true", help="audit without copying")
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parents[1]

    if args.check_only:
        issues = audit_public_files(source)
        if issues:
            print("Public source audit failed:\n- " + "\n- ".join(issues), file=sys.stderr)
            return 1
        files = collect_public_files(source)
        print(f"Public source audit passed ({len(files)} files):")
        for path in files:
            print(f"- {path.relative_to(source).as_posix()}")
        return 0

    if args.output is None:
        parser.error("--output is required unless --check-only is used")
    destination = args.output.expanduser().resolve()
    try:
        count = export_public_tree(source, destination)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Created clean public export with {count} files: {destination}")
    for path in collect_public_files(destination):
        print(f"- {path.relative_to(destination).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
