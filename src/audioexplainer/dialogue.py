"""Dialogue script parser for the two-voice "podcast" mode.

The format uses line-prefixed speaker tags:

    Host: Welcome to the explainer. Today we review the latest commit.
    Guest: Right. The key change fixed the rate-limit bug.

Also tolerates bracketed tags like `[Host]:`. A line with no tag continues the
previous speaker's turn. Keep turns short (<40-50 words) for a dynamic feel.
The engine assigns the first distinct speaker to voice A, the second to voice B.
"""

from __future__ import annotations

import re

_TAG = re.compile(r"^\s*\[?([A-Za-z0-9 _\-]{1,24})\]?:\s*(.+)$")


def parse_dialogue(script: str) -> list[tuple[str, str]]:
    """Return [(speaker, text), ...] in order. Untagged lines extend the prior turn."""
    turns: list[tuple[str, str]] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _TAG.match(line)
        if m:
            turns.append((m.group(1).strip(), m.group(2).strip()))
        elif turns:
            speaker, prev = turns[-1]
            turns[-1] = (speaker, f"{prev} {line}")
        # a leading untagged line with no prior turn is ignored (no speaker yet)
    return turns


def speaker_order(turns: list[tuple[str, str]]) -> list[str]:
    """Distinct speakers in first-seen order (first -> voice A, second -> voice B)."""
    seen: list[str] = []
    for speaker, _ in turns:
        if speaker not in seen:
            seen.append(speaker)
    return seen
