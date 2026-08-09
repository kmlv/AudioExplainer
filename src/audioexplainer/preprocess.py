"""Markdown -> speech-friendly text, plus sentence/paragraph chunking.

Chunking exists because edge-tts is more reliable on bounded inputs and because
the engine concatenates per-chunk audio. This is a conservative baseline.
"""

from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING = re.compile(r"^#{1,6}\s+", re.M)
_LIST_BULLET = re.compile(r"^\s*[-*+]\s+", re.M)
_STRONG_ASTERISK = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_STRONG_UNDERSCORE = re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", re.S)
_EMPHASIS = re.compile(r"(?<!\w)([*_])(?=\S)(.+?)(?<=\S)\1(?!\w)", re.S)
_MULTISPACE = re.compile(r"[ \t]+")
_MULTINEWLINE = re.compile(r"\n{3,}")


def markdown_to_speech(text: str) -> str:
    """Strip markup that should not be read aloud; keep the words."""
    text = _CODE_FENCE.sub(" ", text)        # never read code blocks aloud
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)            # keep anchor text, drop the URL
    text = _INLINE_CODE.sub(r"\1", text)
    text = _HEADING.sub("", text)            # heading words stay, '#' goes
    text = _LIST_BULLET.sub("", text)
    text = _STRONG_ASTERISK.sub(r"\1", text)
    text = _STRONG_UNDERSCORE.sub(r"\1", text)
    text = _EMPHASIS.sub(r"\2", text)        # keep emphasis words, drop */_
    text = _MULTISPACE.sub(" ", text)
    text = _MULTINEWLINE.sub("\n\n", text)
    return text.strip()


def prepare_for_audio(text: str, lang: str = "en") -> dict:
    """Parse math and strip markdown for audio explainer generation."""
    from .math_content import prepare_content
    math_data = prepare_content(text, lang)
    spoken = markdown_to_speech(math_data["spoken_text"])
    return {
        "marked_text": math_data["marked_text"],
        "spoken_text": spoken,
        "formulas": math_data["formulas"]
    }


# RFC default ceiling (codex to tune ~2.5-3.5k).
DEFAULT_CHUNK_CHARS = 3000

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """Return display-ready sentences while preserving paragraph boundaries.

    Providers without boundary events use this shared segmentation for honest
    duration-based transcript following. A paragraph without terminal
    punctuation remains one segment rather than being split arbitrarily.
    """
    sentences: list[str] = []
    for paragraph in re.split(r"\n{2,}", text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences.extend(
            sentence.strip()
            for sentence in _SENT_SPLIT.split(paragraph)
            if sentence.strip()
        )
    return sentences


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """Split into chunks under max_chars at paragraph, then sentence, then (last
    resort) whitespace boundaries."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            flush()
            for sent in _SENT_SPLIT.split(para):
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) > max_chars:
                    flush()
                    chunks.extend(_hard_split(sent, max_chars))
                elif len(buf) + len(sent) + 1 > max_chars:
                    flush()
                    buf = sent
                else:
                    buf = f"{buf} {sent}".strip()
        elif len(buf) + len(para) + 2 > max_chars:
            flush()
            buf = para
        else:
            buf = f"{buf}\n\n{para}".strip()
    flush()
    return chunks


def _hard_split(text: str, max_chars: int) -> list[str]:
    out: list[str] = []
    buf = ""
    for word in text.split():
        if len(buf) + len(word) + 1 > max_chars and buf:
            out.append(buf)
            buf = ""
        buf = f"{buf} {word}".strip()
    if buf:
        out.append(buf)
    return out
