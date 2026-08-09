"""Sensitive-content guard for online synthesis.

Used by the engine to refuse obvious credentials under an explicit online
provider and to route sensitive text through an available local provider in
automatic mode. `--allow-sensitive` bypasses only the local pattern refusal,
never the provider disclosure.
"""

from __future__ import annotations

import re

SENSITIVE_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]", re.I),
    re.compile(r"\bAWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)\b", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),          # OpenAI-style
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),           # GitHub PAT
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),   # Slack
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b.{0,40}(?:password|secret)", re.I),
    re.compile(r"\.env(\.|\b)", re.I),
]


def find_sensitive(text: str) -> list[str]:
    """Return matched snippets (deduped, order-preserving) so callers can report
    what tripped the guard."""
    hits: list[str] = []
    for pat in SENSITIVE_PATTERNS:
        m = pat.search(text)
        if m and m.group(0) not in hits:
            hits.append(m.group(0))
    return hits


def is_sensitive(text: str) -> bool:
    return bool(find_sensitive(text))
