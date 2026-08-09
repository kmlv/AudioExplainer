"""Offline timing and provider-boundary tests for synchronized playback."""

from __future__ import annotations

import subprocess
import sys
import types
import unicodedata
import wave
from pathlib import Path

import pytest

from audioexplainer import engine
from audioexplainer.providers import (
    EdgeProvider,
    PiperProvider,
    ProviderSynthesis,
    SayProvider,
    SpeechBoundary,
)


def _write_wav(path: Path, frames: int, rate: int = engine.SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\0\0" * frames)


def test_edge_stream_writes_audio_and_converts_100ns_ticks(monkeypatch, tmp_path):
    calls = {}

    class FakeCommunicate:
        def __init__(self, text, **kwargs):
            calls["text"] = text
            calls["kwargs"] = kwargs

        async def stream(self):
            yield {"type": "audio", "data": b"ID3"}
            yield {
                "type": "SentenceBoundary",
                "offset": 15_000_000,
                "duration": 2_500_000,
                "text": "Primera frase.",
            }
            yield {"type": "audio", "data": b"payload"}

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate))
    out_path = tmp_path / "edge.mp3"
    result = EdgeProvider().synth("Primera frase.", out_path, "es-MX-DaliaNeural", "+10%")

    assert out_path.read_bytes() == b"ID3payload"
    assert calls["kwargs"]["boundary"] == "SentenceBoundary"
    assert result.boundaries == (SpeechBoundary("Primera frase.", 1.5, 1.75),)


def test_say_returns_no_boundaries(monkeypatch, tmp_path):
    monkeypatch.setattr("audioexplainer.providers.shutil.which", lambda _: "/fake/tool")

    def fake_run(args, **kwargs):
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"mp3")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("audioexplainer.providers.subprocess.run", fake_run)
    result = SayProvider().synth("Sin tiempos.", tmp_path / "say.mp3")

    assert result.audio_path.exists()
    assert result.boundaries is None


def test_piper_runs_locally_and_translates_rate(monkeypatch, tmp_path):
    data_dir = tmp_path / "voices"
    data_dir.mkdir()
    model = data_dir / "es_MX-ald-medium.onnx"
    model.write_bytes(b"model")
    model.with_suffix(".onnx.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AUDIOEXPLAINER_PIPER_DATA_DIR", str(data_dir))
    monkeypatch.setattr("audioexplainer.providers._piper_installed", lambda: True)
    monkeypatch.setattr(
        "audioexplainer.providers.shutil.which",
        lambda name: "/fake/ffmpeg" if name == "ffmpeg" else None,
    )
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"mp3")
        else:
            wav_index = args.index("--output-file") + 1
            _write_wav(Path(args[wav_index]), frames=800)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("audioexplainer.providers.subprocess.run", fake_run)
    result = PiperProvider().synth(
        "Prueba local.", tmp_path / "piper.mp3", "es-MX-DaliaNeural", "+10%"
    )

    piper_call = calls[0]
    scale = float(piper_call[piper_call.index("--length-scale") + 1])
    assert scale == pytest.approx(1 / 1.1, abs=1e-6)
    assert "Prueba local." not in piper_call
    assert result.audio_path.read_bytes() == b"mp3"
    assert result.boundaries is None


def test_wav_duration_uses_frame_count(tmp_path):
    wav_path = tmp_path / "exact.wav"
    _write_wav(wav_path, frames=1_234, rate=8_000)

    assert engine._wav_duration(wav_path) == 1_234 / 8_000


def test_multipart_offsets_use_wav_and_silence_frame_durations(monkeypatch, tmp_path):
    class TimedProvider:
        name = "edge"

        def synth(self, text, out_path, voice, rate):
            Path(out_path).write_bytes(b"audio")
            return ProviderSynthesis(
                Path(out_path), (SpeechBoundary(text, 0.002, 0.008),)
            )

    def fake_to_wav(src, dst):
        # The normalized part WAVs have deliberately non-round durations.
        _write_wav(dst, 240 if src.stem.endswith("000") else 720)

    def fake_silence(dst, pause_ms):
        assert pause_ms == 400
        _write_wav(dst, 480)

    def fake_concat(wavs, target):
        target.write_bytes(b"final audio")

    monkeypatch.setattr(engine, "_validate_audio", lambda _: None)
    monkeypatch.setattr(engine, "_to_wav", fake_to_wav)
    monkeypatch.setattr(engine, "_make_silence", fake_silence)
    monkeypatch.setattr(engine, "_concat_wavs_to_mp3", fake_concat)
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/fake/ffmpeg" if name == "ffmpeg" else None)

    sync = engine._synth_parts(
        TimedProvider(),
        [
            engine._SpeechPart("voice-a", "One.", "Host"),
            engine._SpeechPart("voice-b", "Two.", "Guest"),
        ],
        "voice-a",
        "+10%",
        tmp_path / "combined.mp3",
        pause_ms=400,
    )

    assert sync is not None
    first, second = sync.segments
    assert first.start_s == pytest.approx(0.002)
    # 240 / 24000 part seconds + 480 / 24000 silence seconds + local offset.
    assert second.start_s == pytest.approx(0.01 + 0.02 + 0.002)
    assert [segment.speaker for segment in sync.segments] == ["Host", "Guest"]
    assert [segment.part_index for segment in sync.segments] == [0, 1]


@pytest.mark.parametrize(
    "boundaries",
    [
        None,
        (SpeechBoundary("Different words.", 0.0, 0.5),),
        (SpeechBoundary("Expected words.", float("nan"), 0.5),),
    ],
)
def test_invalid_or_missing_metadata_uses_labelled_estimate(monkeypatch, tmp_path, boundaries):
    class InvalidTimingProvider:
        name = "edge"

        def synth(self, text, out_path, voice, rate):
            Path(out_path).write_bytes(b"audio")
            return ProviderSynthesis(Path(out_path), boundaries)

    monkeypatch.setattr(engine, "_validate_audio", lambda _: None)
    monkeypatch.setattr(engine, "_duration", lambda _: 1.0)
    # Avoid provider-selection/network behavior while keeping the public engine path.
    monkeypatch.setattr(engine, "choose_provider", lambda provider, text: (InvalidTimingProvider(), "fake"))
    result = engine.synth_monologue("Expected words.", out_dir=tmp_path, title="invalid")

    assert result.audio_path.exists()
    assert result.sync is not None
    assert result.sync.source == "duration-weighted-estimate"
    assert [segment.text for segment in result.sync.segments] == ["Expected words."]
    assert result.sync.segments[0].start_s == 0.0
    assert result.sync.segments[0].end_s == 1.0


def test_duration_weighted_estimate_tracks_every_sentence():
    boundaries = engine._estimated_relative_boundaries(
        "Una frase corta. Esta segunda frase tiene bastantes más palabras.\n\nFinal.",
        12.0,
    )

    assert boundaries is not None
    assert [boundary.text for boundary in boundaries] == [
        "Una frase corta.",
        "Esta segunda frase tiene bastantes más palabras.",
        "Final.",
    ]
    assert boundaries[0].start_s == 0.0
    assert boundaries[-1].end_s == 12.0
    assert boundaries[1].end_s - boundaries[1].start_s > boundaries[0].end_s


def test_provider_without_boundaries_gets_estimated_sync(monkeypatch, tmp_path):
    class LocalProvider:
        name = "say"

        def synth(self, text, out_path, voice=None, rate=None):
            Path(out_path).write_bytes(b"audio")
            return ProviderSynthesis(Path(out_path), None)

    monkeypatch.setattr(engine, "_validate_audio", lambda _: None)
    monkeypatch.setattr(engine, "_duration", lambda _: 4.0)

    sync = engine._synth_parts(
        LocalProvider(),
        [engine._SpeechPart("local", "Primera. Segunda oración.")],
        "local",
        "+10%",
        tmp_path / "local.mp3",
    )

    assert sync is not None
    assert sync.source == "duration-weighted-estimate"
    assert [segment.text for segment in sync.segments] == ["Primera.", "Segunda oración."]
    assert sync.segments[-1].end_s == 4.0


def test_spanish_opening_punctuation_restored_from_source_with_provider_timing(monkeypatch, tmp_path):
    # Real Edge 7.2.8 omits unspoken opening ¿/¡ from SentenceBoundary text.
    # The cue must still validate, display the exact source slice (with the
    # inverted marks restored), and keep the provider-measured start/end times.
    class OpeningPunctProvider:
        name = "edge"

        def synth(self, text, out_path, voice, rate):
            Path(out_path).write_bytes(b"audio")
            return ProviderSynthesis(
                Path(out_path),
                (
                    SpeechBoundary("Hola!", 0.0, 0.4),
                    SpeechBoundary("Cómo estás?", 0.6, 1.2),
                ),
            )

    monkeypatch.setattr(engine, "_validate_audio", lambda _: None)
    monkeypatch.setattr(engine, "_duration", lambda _: 2.0)

    sync = engine._synth_parts(
        OpeningPunctProvider(),
        [engine._SpeechPart("es-MX-DaliaNeural", "¡Hola! ¿Cómo estás?")],
        "es-MX-DaliaNeural",
        "+10%",
        tmp_path / "es.mp3",
    )

    assert sync is not None
    assert [seg.text for seg in sync.segments] == ["¡Hola!", "¿Cómo estás?"]
    assert [(seg.start_s, seg.end_s) for seg in sync.segments] == [(0.0, 0.4), (0.6, 1.2)]


def test_opening_quote_restored_but_lexical_mismatch_rejected():
    # Punctuation/whitespace differences are tolerated: the opening curly quote is
    # restored from the source slice.
    restored = engine._validated_relative_boundaries(
        "“Bienvenidos.”",
        (SpeechBoundary("Bienvenidos.", 0.0, 0.5),),
        1.0,
    )
    assert restored is not None
    assert [b.text for b in restored] == ["“Bienvenidos.”"]
    assert (restored[0].start_s, restored[0].end_s) == (0.0, 0.5)

    # A changed letter is lexical content, not punctuation, so it fails closed.
    assert (
        engine._validated_relative_boundaries(
            "Bienvenidos.",
            (SpeechBoundary("Bienvenido.", 0.0, 0.5),),
            1.0,
        )
        is None
    )
    # An inserted word is also rejected.
    assert (
        engine._validated_relative_boundaries(
            "Hola mundo.",
            (SpeechBoundary("Hola gran mundo.", 0.0, 0.5),),
            1.0,
        )
        is None
    )


def test_precomposed_and_decomposed_accents_are_equivalent_and_restored():
    # NFC (precomposed \u00e9) source vs NFD (e + combining acute U+0301) cue:
    # the canonical equivalence is accepted and the source slice is restored.
    nfc = unicodedata.normalize("NFC", "Caf\u00e9.")
    nfd = unicodedata.normalize("NFD", "Caf\u00e9.")
    assert nfc != nfd  # guard: the two forms must actually differ

    restored = engine._validated_relative_boundaries(
        nfc,
        (SpeechBoundary(nfd, 0.0, 0.5),),
        1.0,
    )
    assert restored is not None
    assert [b.text for b in restored] == [nfc]
    assert (restored[0].start_s, restored[0].end_s) == (0.0, 0.5)

    # The reverse direction (decomposed source, precomposed cue) also matches,
    # restoring the exact decomposed source slice verbatim.
    reverse = engine._validated_relative_boundaries(
        nfd,
        (SpeechBoundary(nfc, 0.0, 0.5),),
        1.0,
    )
    assert reverse is not None
    assert [b.text for b in reverse] == [nfd]


def test_deleted_combining_mark_is_rejected():
    # Dropping the combining accent changes content, not just punctuation.
    nfc = unicodedata.normalize("NFC", "Caf\u00e9.")
    assert (
        engine._validated_relative_boundaries(
            nfc,
            (SpeechBoundary("Cafe.", 0.0, 0.5),),
            1.0,
        )
        is None
    )


def test_deleted_variation_selector_is_rejected():
    # U+FE0F is a nonspacing mark; a provider must not silently drop it.
    assert (
        engine._validated_relative_boundaries(
            "A️.",
            (SpeechBoundary("A.", 0.0, 0.5),),
            1.0,
        )
        is None
    )


def test_deleted_zwj_is_rejected():
    # ZWJ (U+200D, format char) joins graphemes and stays significant.
    assert (
        engine._validated_relative_boundaries(
            "A‍B.",
            (SpeechBoundary("AB.", 0.0, 0.5),),
            1.0,
        )
        is None
    )


def test_punctuation_only_cue_is_rejected():
    # A cue whose only characters are punctuation has no content to align.
    assert (
        engine._validated_relative_boundaries(
            "¿?",
            (SpeechBoundary("¿?", 0.0, 0.5),),
            1.0,
        )
        is None
    )


def test_no_space_opening_inverted_question_assigned_to_following_cue():
    # "Hola.¿Cómo?" has no whitespace in the gap; the "." closes the first cue
    # while the inverted "¿" opens the following cue.
    restored = engine._validated_relative_boundaries(
        "Hola.¿Cómo?",
        (
            SpeechBoundary("Hola.", 0.0, 0.4),
            SpeechBoundary("Cómo?", 0.6, 1.2),
        ),
        2.0,
    )
    assert restored is not None
    assert [b.text for b in restored] == ["Hola.", "¿Cómo?"]
    assert [(b.start_s, b.end_s) for b in restored] == [(0.0, 0.4), (0.6, 1.2)]


def test_no_space_opening_quote_assigned_to_following_cue():
    # "Hola.“Adiós.”" has no whitespace in the gap; the opening curly quote goes
    # to the next cue while the trailing closing quote stays with it.
    restored = engine._validated_relative_boundaries(
        "Hola.“Adiós.”",
        (
            SpeechBoundary("Hola.", 0.0, 0.4),
            SpeechBoundary("Adiós.", 0.6, 1.2),
        ),
        2.0,
    )
    assert restored is not None
    assert [b.text for b in restored] == ["Hola.", "“Adiós.”"]
    assert [(b.start_s, b.end_s) for b in restored] == [(0.0, 0.4), (0.6, 1.2)]


def test_math_content_contract_is_used_and_raw_markdown_stays_in_transcript(monkeypatch, tmp_path):
    captured = {}

    class Prepared:
        spoken_text = "La fórmula es x al cuadrado."
        formulas = ({"source": "$x^2$"},)

    class FakeProvider:
        name = "say"

        def synth(self, text, out_path, voice):
            captured["spoken"] = text
            Path(out_path).write_bytes(b"audio")
            return ProviderSynthesis(Path(out_path), None)

    monkeypatch.setitem(
        sys.modules,
        "audioexplainer.math_content",
        types.SimpleNamespace(prepare_content=lambda text, lang: Prepared()),
    )
    monkeypatch.setattr(engine, "choose_provider", lambda provider, text: (FakeProvider(), "fake"))
    monkeypatch.setattr(engine, "_validate_audio", lambda _: None)
    monkeypatch.setattr(engine, "_duration", lambda _: None)

    result = engine.synth_monologue("# Fuente con $x^2$", out_dir=tmp_path)

    assert captured["spoken"] == "La fórmula es x al cuadrado."
    assert result.formulas == ({"source": "$x^2$"},)
    assert "# Fuente con $x^2$" in result.transcript_path.read_text(encoding="utf-8")
