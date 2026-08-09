"""Core synthesis: provider selection, multipart assembly, and optional sync.

Provider timing is deliberately provider-neutral. Exact sentence events are
preserved when available; providers without them receive duration-weighted,
explicitly labelled estimated timing so every generated voice can follow the
transcript.
"""

from __future__ import annotations

import datetime
import math
import re
import shutil
import socket
import subprocess
import tempfile
import unicodedata
import wave
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Iterable, Iterator

from . import dialogue as dialogue_mod
from . import preprocess, safety, voices
from .providers import (
    EdgeProvider,
    PiperProvider,
    ProviderError,
    ProviderSynthesis,
    SayProvider,
    SpeechBoundary,
    rate_multiplier,
)

DEFAULT_OUT_DIR = Path(tempfile.gettempdir()) / "audioexplainer"
# +10% = 1.1x normal speed. Override per call with --rate (for example, "+0%"
# for slower or "+20%" for faster).
DEFAULT_RATE = "+10%"
_EDGE_PROBE_HOST = "speech.platform.bing.com"

# Normalized-concat pipeline: synth parts -> normalize each to WAV PCM mono @
# SAMPLE_RATE -> insert silence pads -> concat -> final MP3.
SAMPLE_RATE = 24000
MP3_BITRATE = "64k"
PARAGRAPH_PAUSE_MS = 300
DIALOGUE_PAUSE_MS = 400
_MIN_AUDIO_BYTES = 800


@dataclass(frozen=True)
class TimedSegment:
    """One spoken sentence on the final media timeline, in seconds."""

    text: str
    start_s: float
    end_s: float
    part_index: int
    speaker: str | None = None


@dataclass(frozen=True)
class SyncTrack:
    """Provider-neutral sentence timing suitable for a media player or sidecar."""

    segments: tuple[TimedSegment, ...]
    granularity: str = "sentence"
    source: str = "unknown"
    timebase: str = "media_seconds"


@dataclass
class SynthResult:
    audio_path: Path
    transcript_path: Path
    provider: str
    provider_reason: str
    duration_s: float | None
    n_parts: int
    # Defaults preserve the original positional six-field construction API.
    sync: SyncTrack | None = None
    formulas: tuple[object, ...] = ()


@dataclass(frozen=True)
class _SpeechPart:
    """Internal input to one provider request; speaker is not part of cue text."""

    voice: str
    text: str
    speaker: str | None = None

    def __iter__(self) -> Iterator[str]:
        """Keep legacy two-item unpacking used by engine test doubles working."""
        yield self.voice
        yield self.text


@dataclass(frozen=True)
class _PreparedContent:
    spoken_text: str
    formulas: tuple[object, ...] = ()


# --------------------------------------------------------------------------- #
# Provider selection (D1 = auto)
# --------------------------------------------------------------------------- #
def _network_ok(host: str = _EDGE_PROBE_HOST, port: int = 443, timeout: float = 2.0) -> bool:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


def choose_provider(provider: str, text: str):
    """Return (provider_obj, reason). Implements the D1 auto policy."""
    edge, piper, say = EdgeProvider(), PiperProvider(), SayProvider()
    if provider == "edge":
        if not edge.available():
            raise ProviderError("--provider edge requested but edge-tts is not installed")
        return edge, "edge (explicit)"
    if provider == "piper":
        if not piper.available():
            raise ProviderError(
                "--provider piper requested but its local neural voice is not ready; "
                "run `audioexplain --setup-piper`"
            )
        return piper, "piper (explicit, local neural)"
    if provider == "say":
        return say, "say (explicit)"
    if safety.is_sensitive(text):
        if piper.available():
            return piper, "piper (auto: sensitive content stays local)"
        return say, "say (auto: sensitive content detected)"
    if edge.available() and _network_ok():
        return edge, "edge (auto)"
    if piper.available():
        return piper, "piper (auto: edge/network unavailable)"
    return say, "say (auto: edge/network unavailable)"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def synth_monologue(
    text: str,
    voice: str = voices.DEFAULT_EDGE_VOICE_ES,
    rate: str = DEFAULT_RATE,
    provider: str = "auto",
    out_path: str | Path | None = None,
    out_dir: str | Path | None = None,
    title: str = "audio explainer",
    allow_sensitive: bool = False,
    lang: str | None = None,
) -> SynthResult:
    rate_multiplier(rate)
    voice = voices.resolve_voice(voice)
    content = _prepare_content(text, lang or voices.lang_of(voice))
    if not content.spoken_text:
        raise ValueError("no text to synthesize after preprocessing")
    _guard(text, provider, allow_sensitive)

    chunks = preprocess.chunk_text(content.spoken_text)
    target = _resolve_out_path(out_path, out_dir, title)
    prov, reason, sync = _synth_with_fallback(
        provider,
        text,
        [_SpeechPart(voice, chunk) for chunk in chunks],
        voice,
        rate,
        target,
        pause_ms=PARAGRAPH_PAUSE_MS,
    )
    # The Markdown source remains the transcript artifact; only the provider
    # receives the math-aware spoken form.
    transcript = _write_transcript(target, title, text, prov.name, reason)
    return SynthResult(
        target,
        transcript,
        prov.name,
        reason,
        _duration(target),
        len(chunks),
        sync=sync,
        formulas=content.formulas,
    )


def synth_dialogue(
    script: str,
    voice_a: str | None = None,
    voice_b: str | None = None,
    lang: str = "es",
    rate: str = DEFAULT_RATE,
    provider: str = "auto",
    out_path: str | Path | None = None,
    out_dir: str | Path | None = None,
    title: str = "audio explainer",
    allow_sensitive: bool = False,
) -> SynthResult:
    rate_multiplier(rate)
    turns = dialogue_mod.parse_dialogue(script)
    if not turns:
        raise ValueError("no dialogue turns parsed; expected lines like 'Host: ...'")

    pair_a, pair_b = voices.dialogue_pair(lang)
    voice_a = voices.resolve_voice(voice_a) if voice_a else pair_a
    voice_b = voices.resolve_voice(voice_b) if voice_b else pair_b
    speakers = dialogue_mod.speaker_order(turns)
    voice_for = {sp: (voice_a if i % 2 == 0 else voice_b) for i, sp in enumerate(speakers)}

    full_text = "\n".join(f"{sp}: {line}" for sp, line in turns)
    _guard(full_text, provider, allow_sensitive)
    parts: list[_SpeechPart] = []
    formulas: list[object] = []
    for speaker, line in turns:
        content = _prepare_content(line, lang)
        formulas.extend(content.formulas)
        if content.spoken_text.strip():
            parts.append(_SpeechPart(voice_for[speaker], content.spoken_text, speaker))
    target = _resolve_out_path(out_path, out_dir, title)
    prov, reason, sync = _synth_with_fallback(
        provider,
        full_text,
        parts,
        voice_a,
        rate,
        target,
        pause_ms=DIALOGUE_PAUSE_MS,
    )
    # Preserve the raw submitted dialogue script when possible, including
    # Markdown the dialogue parser does not need to send verbatim to TTS.
    transcript = _write_transcript(target, title, script, prov.name, reason)
    return SynthResult(
        target,
        transcript,
        prov.name,
        reason,
        _duration(target),
        len(parts),
        sync=sync,
        formulas=tuple(formulas),
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _prepare_content(text: str, lang: str) -> _PreparedContent:
    """Use the optional math layer when available, with a safe local fallback."""
    try:
        from .math_content import prepare_content
    except (ImportError, ModuleNotFoundError):
        return _PreparedContent(preprocess.markdown_to_speech(text))

    prepared = prepare_content(text, lang)
    if isinstance(prepared, Mapping):
        spoken_text = prepared.get("spoken_text")
        raw_formulas = prepared.get("formulas", ())
    else:
        spoken_text = getattr(prepared, "spoken_text", None)
        raw_formulas = getattr(prepared, "formulas", ())
    if not isinstance(spoken_text, str):
        # During staged rollout a partial module should not make ordinary audio
        # unusable.  A complete module always supplies the agreed attribute.
        return _PreparedContent(preprocess.markdown_to_speech(text))
    if raw_formulas is None:
        formulas: tuple[object, ...] = ()
    else:
        try:
            formulas = tuple(raw_formulas)
        except TypeError:
            formulas = (raw_formulas,)
    return _PreparedContent(preprocess.markdown_to_speech(spoken_text), formulas)


def _guard(text: str, provider: str, allow_sensitive: bool) -> None:
    if allow_sensitive:
        return
    hits = safety.find_sensitive(text)
    if hits and provider == "edge":
        raise ProviderError(
            f"refusing: sensitive content detected ({hits[0]!r}). "
            "Use --provider piper/say (offline) or --allow-sensitive to override."
        )


def _synth_with_fallback(
    provider: str,
    text: str,
    parts: list[_SpeechPart],
    default_voice: str,
    rate: str,
    target: Path,
    *,
    pause_ms: int,
):
    """Synthesize with the selected provider and retry local fallbacks in auto mode."""
    primary, primary_reason = choose_provider(provider, text)
    candidates: list[tuple[object, str]] = [(primary, primary_reason)]

    if provider == "auto" and primary.name in {"edge", "piper"}:
        piper = PiperProvider()
        if primary.name != "piper" and all(piper.available_for(part.voice) for part in parts):
            candidates.append((piper, "piper (auto neural fallback)"))
        say = SayProvider()
        if primary.name != "say" and say.available():
            candidates.append((say, "say (auto system fallback)"))

    failures: list[str] = []
    seen: set[str] = set()
    for candidate, reason in candidates:
        if candidate.name in seen:
            continue
        seen.add(candidate.name)
        target.unlink(missing_ok=True)
        try:
            candidate_parts = _parts_for_provider(candidate.name, parts)
            sync = _synth_parts(
                candidate,
                candidate_parts,
                default_voice,
                rate,
                target,
                pause_ms=pause_ms,
            )
        except ProviderError as e:
            failures.append(f"{candidate.name}: {e}")
            if provider != "auto":
                raise
            continue
        if failures:
            failed_names = ", ".join(item.split(":", 1)[0] for item in failures)
            reason = f"{reason[:-1]}, after {failed_names} failed)" if reason.endswith(")") else reason
        return candidate, reason, sync

    detail = "; ".join(failures) or "no usable provider is installed"
    raise ProviderError(f"automatic TTS fallback chain failed: {detail}")


def _parts_for_provider(provider_name: str, parts: list[_SpeechPart]) -> list[_SpeechPart]:
    """Preserve paragraph pauses for providers without native boundaries."""
    if provider_name not in {"piper", "say"}:
        return parts
    expanded: list[_SpeechPart] = []
    for part in parts:
        paragraphs = [item.strip() for item in re.split(r"\n{2,}", part.text) if item.strip()]
        expanded.extend(_SpeechPart(part.voice, paragraph, part.speaker) for paragraph in paragraphs)
    return expanded


def _validate_audio(path: Path) -> None:
    """Reject silent / metadata-only output from a provider."""
    if not path.exists() or path.stat().st_size < _MIN_AUDIO_BYTES:
        raise ProviderError(
            f"synthesis produced no usable audio at {path} "
            "(provider may have failed silently — try a local provider or check --doctor)"
        )
    if shutil.which("ffprobe"):
        dur = _duration(path)
        if dur is None or dur <= 0.05:
            raise ProviderError(
                f"synthesis produced empty/unreadable audio at {path} "
                "(provider may have failed silently)"
            )


def _synth_one(prov, voice: str, text: str, out_path: Path, rate: str) -> ProviderSynthesis:
    if prov.name == "say":
        result = prov.synth(text, out_path, voice=voices.SAY_VOICE[voices.lang_of(voice)])
    else:
        result = prov.synth(text, out_path, voice=voice, rate=rate)
    return _coerce_provider_synthesis(result, out_path)


def _coerce_provider_synthesis(result, fallback_path: Path) -> ProviderSynthesis:
    """Accept legacy Path-returning test doubles during the result-object migration."""
    if isinstance(result, ProviderSynthesis):
        return result
    if result is None:
        return ProviderSynthesis(fallback_path, None)
    return ProviderSynthesis(Path(result), None)


def _as_speech_part(part) -> _SpeechPart:
    if isinstance(part, _SpeechPart):
        return part
    voice, text = part
    return _SpeechPart(voice, text)


def _synth_parts(
    prov,
    parts: Iterable[_SpeechPart | tuple[str, str]],
    default_voice: str,
    rate: str,
    target: Path,
    pause_ms: int = PARAGRAPH_PAUSE_MS,
) -> SyncTrack | None:
    """Synthesize parts and return exact or explicitly estimated sentence sync.

    Multipart offsets are calculated from decoded WAV frame counts and silence
    WAV frame counts.  They are never scaled to the final MP3 duration.
    """
    del default_voice  # retained for the pre-existing internal call signature
    target.parent.mkdir(parents=True, exist_ok=True)
    speech_parts = [_as_speech_part(part) for part in parts]
    speech_parts = [part for part in speech_parts if part.text.strip()]
    if not speech_parts:
        raise ValueError("nothing to synthesize")

    if len(speech_parts) == 1:
        part = speech_parts[0]
        synthesis = _synth_one(prov, part.voice, part.text, target, rate)
        _validate_audio(synthesis.audio_path)
        return _build_sync_track(
            speech_parts,
            [synthesis],
            [_duration(synthesis.audio_path)],
            silence_s=0.0,
        )

    if shutil.which("ffmpeg") is None:
        raise ProviderError("ffmpeg required to assemble multi-part audio")
    with tempfile.TemporaryDirectory(prefix="audioexplainer-") as td:
        tmp = Path(td)
        wavs: list[Path] = []
        syntheses: list[ProviderSynthesis] = []
        durations: list[float | None] = []
        for i, part in enumerate(speech_parts):
            piece = tmp / f"part_{i:03d}.mp3"
            synthesis = _synth_one(prov, part.voice, part.text, piece, rate)
            _validate_audio(synthesis.audio_path)
            wav = tmp / f"part_{i:03d}.wav"
            _to_wav(synthesis.audio_path, wav)
            syntheses.append(synthesis)
            wavs.append(wav)
            durations.append(_wav_duration(wav))

        silence = tmp / "silence.wav"
        _make_silence(silence, pause_ms)
        silence_s = _wav_duration(silence)
        sequence: list[Path] = []
        for i, wav in enumerate(wavs):
            sequence.append(wav)
            if i != len(wavs) - 1:
                sequence.append(silence)
        _concat_wavs_to_mp3(sequence, target)

    _validate_audio(target)
    if silence_s is None:
        return None
    return _build_sync_track(speech_parts, syntheses, durations, silence_s=silence_s)


def _build_sync_track(
    parts: Iterable[_SpeechPart],
    syntheses: Iterable[ProviderSynthesis],
    part_durations_s: Iterable[float | None],
    *,
    silence_s: float,
) -> SyncTrack | None:
    """Validate part metadata and place it on the concatenated media timeline.

    Exact provider boundaries win. When they are missing or invalid, the part's
    decoded duration is divided across its sentences by spoken-text weight.
    The track source records whether timing is exact, estimated, or mixed.
    """
    part_list = list(parts)
    synthesis_list = list(syntheses)
    durations = list(part_durations_s)
    if len(part_list) != len(synthesis_list) or len(part_list) != len(durations):
        return None
    if not _is_finite_nonnegative(silence_s):
        return None

    timeline_s = 0.0
    segments: list[TimedSegment] = []
    timing_kinds: set[str] = set()
    for part_index, (part, synthesis, duration_s) in enumerate(
        zip(part_list, synthesis_list, durations)
    ):
        if duration_s is not None and not _is_finite_nonnegative(duration_s):
            return None
        relative = _validated_relative_boundaries(part.text, synthesis.boundaries, duration_s)
        if relative is None:
            relative = _estimated_relative_boundaries(part.text, duration_s)
            if relative is None:
                return None
            timing_kinds.add("estimated")
        else:
            timing_kinds.add("exact")
        for boundary in relative:
            end_s = boundary.end_s if duration_s is None else min(boundary.end_s, duration_s)
            if end_s < boundary.start_s:
                return None
            segments.append(
                TimedSegment(
                    text=boundary.text,
                    start_s=timeline_s + boundary.start_s,
                    end_s=timeline_s + end_s,
                    part_index=part_index,
                    speaker=part.speaker,
                )
            )
        if duration_s is None:
            # Multipart construction always has WAV durations; a missing one is
            # a sync-only failure rather than a reason to discard good audio.
            if len(part_list) > 1:
                return None
        else:
            timeline_s += duration_s
        if part_index != len(part_list) - 1:
            timeline_s += silence_s
    if timing_kinds == {"exact"}:
        source = "edge-sentence-boundary"
    elif timing_kinds == {"estimated"}:
        source = "duration-weighted-estimate"
    else:
        source = "mixed-boundary-estimate"
    return SyncTrack(tuple(segments), source=source)


def _estimated_relative_boundaries(
    spoken_text: str,
    duration_s: float | None,
) -> tuple[SpeechBoundary, ...] | None:
    """Allocate decoded audio duration across sentences by spoken-text weight."""
    if duration_s is None or not math.isfinite(duration_s) or duration_s <= 0:
        return None
    sentences = preprocess.split_sentences(spoken_text)
    if not sentences:
        return None

    # Words approximate articulation time; punctuation adds a small pause
    # weight without allowing short interjections to collapse to zero length.
    weights = [
        max(
            1.0,
            len(re.findall(r"\w+", sentence))
            + 0.35 * len(re.findall(r"[.!?…,:;]", sentence)),
        )
        for sentence in sentences
    ]
    total_weight = sum(weights)
    elapsed_weight = 0.0
    boundaries: list[SpeechBoundary] = []
    for index, (sentence, weight) in enumerate(zip(sentences, weights)):
        start_s = duration_s * elapsed_weight / total_weight
        elapsed_weight += weight
        end_s = (
            duration_s
            if index == len(sentences) - 1
            else duration_s * elapsed_weight / total_weight
        )
        boundaries.append(SpeechBoundary(sentence, start_s, end_s))
    return tuple(boundaries)


def _validated_relative_boundaries(
    spoken_text: str,
    boundaries: tuple[SpeechBoundary, ...] | None,
    duration_s: float | None,
) -> tuple[SpeechBoundary, ...] | None:
    if not spoken_text.strip() or not boundaries:
        return None
    previous_start = -math.inf
    for boundary in boundaries:
        if not isinstance(boundary, SpeechBoundary):
            return None
        if not boundary.text.strip():
            return None
        if not (_is_finite_nonnegative(boundary.start_s) and _is_finite_nonnegative(boundary.end_s)):
            return None
        if boundary.end_s < boundary.start_s or boundary.start_s < previous_start:
            return None
        if duration_s is not None and boundary.start_s > duration_s:
            return None
        previous_start = boundary.start_s
    return _restore_boundaries_from_source(spoken_text, boundaries)


def _restore_boundaries_from_source(
    spoken_text: str,
    boundaries: tuple[SpeechBoundary, ...],
) -> tuple[SpeechBoundary, ...] | None:
    """Fail-closed content validation with exact source-slice text restoration.

    Providers such as Edge omit *unspoken* opening punctuation (Spanish inverted
    ``¿``/``¡``, opening curly quotes) from ``SentenceBoundary`` text, so a
    literal concatenation comparison rejects otherwise-measured cues.  We instead
    compare all Unicode content except punctuation and whitespace, accepting
    canonical NFC/NFD equivalence: each source character is normalized to NFD and
    every resulting code point is retained unless it is punctuation (``P*``) or
    whitespace.  Marks (combining accents), variation selectors, and ZWJ/format
    characters therefore stay significant, so a dropped combining mark, variation
    selector, or ZWJ is rejected even though a precomposed/decomposed accent pair
    still matches.  Any missing, inserted, reordered, or altered content code
    point fails closed.  When the content matches, each cue's displayed text is
    restored from the exact source slice while its provider-measured start/end
    times are retained.
    """
    source_content: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(spoken_text):
        for code_point in unicodedata.normalize("NFD", char):
            if _is_significant_content(code_point):
                source_content.append(code_point)
                # Map every retained code point back to its original source
                # character index so restoration slices the exact source text.
                positions.append(index)

    boundary_contents = [_significant_content(boundary.text) for boundary in boundaries]
    # A cue with no significant content cannot be aligned to a source slice.
    if any(not content for content in boundary_contents):
        return None
    if [cp for content in boundary_contents for cp in content] != source_content:
        return None

    restored: list[SpeechBoundary] = []
    slice_start = 0
    consumed = 0
    last_index = len(boundaries) - 1
    for i, (boundary, content) in enumerate(zip(boundaries, boundary_contents)):
        consumed += len(content)
        if i == last_index:
            slice_end = len(spoken_text)
        else:
            # Keep this cue's trailing (closing) punctuation but hand the next
            # cue's opening punctuation (``¿``/``¡``/opening quotes) to the next
            # slice, even when no whitespace separates the two cues' content.
            gap_start = positions[consumed - 1] + 1
            next_content_start = positions[consumed]
            slice_end = next_content_start
            # Pull back over any run of opening punctuation directly preceding
            # the next cue's content so it displays with the following cue.
            k = next_content_start
            while k > gap_start and _is_opening_punctuation(spoken_text[k - 1]):
                k -= 1
            slice_end = k
            # If whitespace separates the cues, split at the first whitespace so
            # the previous cue does not absorb trailing spaces.
            for j in range(gap_start, slice_end):
                if spoken_text[j].isspace():
                    slice_end = j
                    break
        display_text = spoken_text[slice_start:slice_end].strip()
        if not display_text:
            return None
        restored.append(SpeechBoundary(display_text, boundary.start_s, boundary.end_s))
        slice_start = slice_end
    return tuple(restored)


# Spanish inverted marks are ``Po`` (not ``Ps``/``Pi``) yet open a clause, so
# they are treated as opening punctuation explicitly.
_EXPLICIT_OPENING_PUNCTUATION = frozenset("¿¡")  # ¿ ¡


def _significant_content(text: str) -> list[str]:
    """Return the NFD-normalized content code points of ``text``.

    Punctuation and whitespace are dropped; everything else — letters, numbers,
    symbols, marks, variation selectors, and format characters — is retained.
    """
    return [
        code_point
        for char in text
        for code_point in unicodedata.normalize("NFD", char)
        if _is_significant_content(code_point)
    ]


def _is_significant_content(char: str) -> bool:
    """True for any code point that is neither punctuation nor whitespace.

    Provider punctuation/spacing normalization is tolerated, but marks,
    variation selectors, and ZWJ/format characters stay significant so a
    provider cannot silently drop or alter them.
    """
    return not (unicodedata.category(char).startswith("P") or char.isspace())


def _is_opening_punctuation(char: str) -> bool:
    """True for opening/initial punctuation handed to the following cue.

    Unicode ``Ps`` (open) and ``Pi`` (initial quote) plus the Spanish inverted
    ``¿``/``¡`` marks, which open a clause but classify as ``Po``.
    """
    return unicodedata.category(char) in ("Ps", "Pi") or char in _EXPLICIT_OPENING_PUNCTUATION


def _is_finite_nonnegative(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _to_wav(src: Path, dst: Path) -> None:
    _run_ffmpeg(
        ["-i", str(src), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", str(dst)],
        what="normalize to wav",
    )


def _make_silence(dst: Path, pause_ms: int) -> None:
    seconds = max(pause_ms, 0) / 1000.0
    _run_ffmpeg(
        ["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{seconds:.3f}", str(dst)],
        what="generate silence",
    )


def _concat_wavs_to_mp3(wavs: list[Path], target: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as mf:
        for wav_path in wavs:
            mf.write(f"file '{wav_path}'\n")
        manifest = mf.name
    try:
        _run_ffmpeg(
            [
                "-f", "concat", "-safe", "0", "-i", manifest,
                "-ac", "1", "-ar", str(SAMPLE_RATE), "-codec:a", "libmp3lame", "-b:a", MP3_BITRATE,
                str(target),
            ],
            what="concat",
        )
    finally:
        Path(manifest).unlink(missing_ok=True)


def _run_ffmpeg(args: list[str], what: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise ProviderError("ffmpeg required to assemble audio")
    try:
        subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", "ignore") if e.stderr else ""
        raise ProviderError(f"ffmpeg {what} failed: {stderr or e}") from e


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:40] or "audio"


def _resolve_out_path(out_path, out_dir, title) -> Path:
    if out_path:
        return Path(out_path).expanduser().resolve()
    base = Path(out_dir).expanduser() if out_dir else DEFAULT_OUT_DIR
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return (base / f"{ts}_{_slug(title)}.mp3").resolve()


def _write_transcript(audio_path: Path, title: str, text: str, provider: str, reason: str) -> Path:
    transcript_path = audio_path.with_suffix(".md")
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        f"# {title}\n\n_Generated by audioexplainer — provider: {provider} ({reason})_\n\n{text}\n",
        encoding="utf-8",
    )
    return transcript_path


def _duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None or not path.exists():
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def _wav_duration(path: Path) -> float | None:
    """Return the exact decoded WAV duration from frame count, not ffprobe's float."""
    try:
        with wave.open(str(path), "rb") as wav_file:
            rate = wav_file.getframerate()
            if rate <= 0:
                return None
            return wav_file.getnframes() / rate
    except (OSError, EOFError, wave.Error):
        return None
