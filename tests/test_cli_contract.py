"""Conformance tests for the audioexplain CLI contract + core engine.

These run WITHOUT network, edge-tts, or ffmpeg by using a fake provider and
single-part (no-concat) inputs. Additional suites cover provider-level and
multi-part concat tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audioexplainer import cli, dialogue, engine, preprocess, safety
from audioexplainer.providers import ProviderError


# --- preprocessing -------------------------------------------------------- #
def test_markdown_to_speech_strips_code_and_urls():
    out = preprocess.markdown_to_speech(
        "# Title\n\nUse `foo()` and **run it**, not *read it*.\n\n```\nsecret code\n```\n\nSee [the docs](http://x.com)."
    )
    assert "Title" in out
    assert "run it" in out and "read it" in out
    assert "**" not in out and "*read" not in out
    assert "secret code" not in out      # code fences never read aloud
    assert "the docs" in out             # link anchor text kept
    assert "http" not in out             # url dropped


def test_markdown_to_speech_preserves_intraword_markers():
    out = preprocess.markdown_to_speech(
        "Keep snake_case_names, a*b*c, and a__b__c; remove *spoken emphasis* and **strong**word."
    )
    assert "snake_case_names" in out
    assert "a*b*c" in out
    assert "a__b__c" in out
    assert "spoken emphasis" in out
    assert "*spoken emphasis*" not in out
    assert "strongword" in out
    assert "**" not in out


def test_chunk_text_splits_long_input():
    text = ("This is a sentence. " * 500).strip()
    chunks = preprocess.chunk_text(text, max_chars=400)
    assert len(chunks) > 1
    assert all(len(c) <= 450 for c in chunks)  # small slack for boundaries


def test_chunk_text_short_stays_single():
    assert preprocess.chunk_text("Short.") == ["Short."]


# --- dialogue parsing ----------------------------------------------------- #
def test_dialogue_parse_tags_and_continuation():
    turns = dialogue.parse_dialogue("Host: Hello there.\n[Guest]: Hi!\nStill the guest talking.")
    assert turns[0] == ("Host", "Hello there.")
    assert turns[1][0] == "Guest"
    assert "Still the guest talking" in turns[1][1]


def test_speaker_order():
    turns = [("A", "x"), ("B", "y"), ("A", "z")]
    assert dialogue.speaker_order(turns) == ["A", "B"]


# --- safety --------------------------------------------------------------- #
def test_sensitive_detection():
    assert safety.is_sensitive("export API_KEY=abc123")
    assert safety.is_sensitive("the password: hunter2")
    assert not safety.is_sensitive("A normal explainer about today's commits.")


# --- provider selection (D1 auto) ----------------------------------------- #
def test_auto_routes_sensitive_to_local_neural_when_ready(monkeypatch):
    monkeypatch.setattr(engine.PiperProvider, "available", lambda self: True)
    prov, reason = engine.choose_provider("auto", "my password: hunter2")
    assert prov.name == "piper"
    assert "sensitive" in reason


def test_auto_routes_sensitive_to_system_voice_without_piper(monkeypatch):
    monkeypatch.setattr(engine.PiperProvider, "available", lambda self: False)
    prov, reason = engine.choose_provider("auto", "my password: hunter2")
    assert prov.name == "say"
    assert "sensitive" in reason


def test_edge_explicit_requires_edge(monkeypatch):
    monkeypatch.setattr(engine.EdgeProvider, "available", lambda self: False)
    with pytest.raises(ProviderError):
        engine.choose_provider("edge", "hello")


def test_auto_prefers_local_neural_piper_when_edge_is_unavailable(monkeypatch):
    monkeypatch.setattr(engine.EdgeProvider, "available", lambda self: False)
    monkeypatch.setattr(engine.PiperProvider, "available", lambda self: True)

    prov, reason = engine.choose_provider("auto", "ordinary text")

    assert prov.name == "piper"
    assert "edge/network unavailable" in reason


def test_auto_retries_piper_when_edge_synthesis_fails(tmp_path, monkeypatch):
    class FailingEdge:
        name = "edge"

        def synth(self, text, out_path, voice=None, rate=None):
            raise ProviderError("temporary service failure")

    class WorkingPiper:
        name = "piper"

        def available_for(self, voice):
            return True

        def synth(self, text, out_path, voice=None, rate=None):
            Path(out_path).write_bytes(b"ID3local-neural-audio")
            return out_path

    monkeypatch.setattr(
        engine, "choose_provider", lambda provider, text: (FailingEdge(), "edge (auto)")
    )
    monkeypatch.setattr(engine, "PiperProvider", WorkingPiper)
    monkeypatch.setattr(engine, "_validate_audio", lambda path: None)
    monkeypatch.setattr(engine, "_duration", lambda path: 1.0)

    result = engine.synth_monologue(
        "Fallback test.", out_dir=tmp_path, title="fallback"
    )

    assert result.provider == "piper"
    assert "after edge failed" in result.provider_reason
    assert result.audio_path.read_bytes() == b"ID3local-neural-audio"


def test_sensitive_auto_fallback_never_synthesizes_with_edge(tmp_path, monkeypatch):
    edge_calls = []

    class ForbiddenEdge:
        name = "edge"

        def available(self):
            return True

        def synth(self, *args, **kwargs):
            edge_calls.append((args, kwargs))
            raise AssertionError("sensitive text reached Edge")

    class FailingPiper:
        name = "piper"

        def available(self):
            return True

        def synth(self, *args, **kwargs):
            raise ProviderError("local model failure")

    class WorkingSay:
        name = "say"

        def available(self):
            return True

        def synth(self, text, out_path, voice=None):
            Path(out_path).write_bytes(b"ID3offline-system-audio")
            return out_path

    monkeypatch.setattr(engine, "EdgeProvider", ForbiddenEdge)
    monkeypatch.setattr(engine, "PiperProvider", FailingPiper)
    monkeypatch.setattr(engine, "SayProvider", WorkingSay)
    monkeypatch.setattr(engine, "_validate_audio", lambda path: None)
    monkeypatch.setattr(engine, "_duration", lambda path: 1.0)

    result = engine.synth_monologue(
        "the password: hunter2", out_dir=tmp_path, title="private"
    )

    assert result.provider == "say"
    assert edge_calls == []


@pytest.mark.parametrize("provider_name", ["piper", "say"])
def test_local_provider_parts_preserve_paragraph_boundaries(provider_name):
    parts = [engine._SpeechPart("es-MX-DaliaNeural", "Primero.\n\nSegundo.")]
    expanded = engine._parts_for_provider(provider_name, parts)
    assert [part.text for part in expanded] == ["Primero.", "Segundo."]
    assert engine._parts_for_provider("edge", parts) == parts


# --- engine + CLI contract (fake provider, no network/ffmpeg) ------------- #
class _FakeProvider:
    name = "fake"

    def available(self):
        return True

    def synth(self, text, out_path, voice=None, rate=None):
        Path(out_path).write_bytes(b"ID3fake-audio")
        return out_path


@pytest.fixture
def fake_provider(monkeypatch):
    monkeypatch.setattr(engine, "choose_provider", lambda provider, text: (_FakeProvider(), "fake"))
    # fake bytes are not real audio; the contract tests don't validate audio.
    monkeypatch.setattr(engine, "_validate_audio", lambda path: None)


class _TrivialProvider:
    """Mimics a provider that exits 0 but writes unusable audio (codex blocker)."""

    name = "trivial"

    def available(self):
        return True

    def synth(self, text, out_path, voice=None, rate=None):
        Path(out_path).write_bytes(b"ID3" + b"\x00" * 20)  # metadata-only, ~23 bytes
        return out_path


def test_validate_audio_rejects_trivial_output(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"ID3" + b"\x00" * 40)
    with pytest.raises(ProviderError):
        engine._validate_audio(bad)


def test_engine_rejects_silent_provider_output(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "choose_provider", lambda provider, text: (_TrivialProvider(), "trivial"))
    with pytest.raises(ProviderError):
        engine.synth_monologue("Hello there, this should fail validation.", out_dir=tmp_path)


def test_engine_writes_audio_and_transcript(tmp_path, fake_provider):
    res = engine.synth_monologue("Hello world, this is a test.", out_dir=tmp_path, title="demo")
    assert res.audio_path.exists() and res.audio_path.suffix == ".mp3"
    assert res.transcript_path.exists() and res.transcript_path.suffix == ".md"
    assert "demo" in res.transcript_path.read_text()


def test_cli_final_stdout_line_is_mp3_path(tmp_path, fake_provider, capsys):
    rc = cli.main(["Hello.", "--out-dir", str(tmp_path), "--title", "t"])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1].endswith(".mp3")
    assert Path(lines[-1]).exists()
    player = Path(lines[-1]).with_suffix(".player.html")
    assert player.exists()
    html = player.read_text(encoding="utf-8")
    assert "data-skip=\"-15\"" in html
    assert "data-skip=\"-10\"" in html
    assert "data-skip=\"-5\"" in html
    assert "data-skip=\"5\"" in html
    assert "data-skip=\"10\"" in html
    assert "data-skip=\"15\"" in html
    assert 'class="speed-stepper" role="group" aria-label="Velocidad de reproducción"' in html
    assert 'id="rateDown"' in html
    assert 'id="rateReset"' in html
    assert 'id="rateUp"' in html
    assert "const MIN_RATE_STEPS = 15;" in html
    assert "const MAX_RATE_STEPS = 40;" in html
    assert "Math.round(Number(audio.playbackRate) * 20)" in html
    assert 'rateReset.addEventListener("keydown"' in html
    assert 'data-speed=' not in html
    assert "fetch(safeAudio" in html
    assert "safeLocalHref(data.audio)" in html
    assert "URL.createObjectURL(blob)" in html
    assert "transcriptText" in html
    assert "Hello." in html
    sidecar = json.loads(Path(lines[-1]).with_suffix(".audio.json").read_text(encoding="utf-8"))
    assert sidecar["duration_s"] is None


def test_cli_dialogue_contract(tmp_path, fake_provider, capsys):
    rc = cli.main([
        "Host: Welcome. Guest: Thanks for having me.",
        "--style", "dialogue", "--out-dir", str(tmp_path),
    ])
    # single line with both tags -> parsed into one turn; fake provider, single file
    assert rc == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].endswith(".mp3")


def test_dialogue_assigns_two_distinct_voices(tmp_path, monkeypatch):
    """Exercise multi-voice assignment (Host -> A, Guest -> B) without
    needing ffmpeg, by capturing the parts the engine would synthesize."""
    captured = {}

    def fake_synth_parts(prov, parts, default_voice, rate, target, pause_ms=0):
        captured["parts"] = parts
        Path(target).write_bytes(b"x")

    monkeypatch.setattr(engine, "choose_provider", lambda provider, text: (_FakeProvider(), "fake"))
    monkeypatch.setattr(engine, "_synth_parts", fake_synth_parts)
    engine.synth_dialogue("Host: Hi there.\nGuest: Hello back.", lang="es", out_dir=tmp_path)
    voices_used = [v for v, _ in captured["parts"]]
    assert len(voices_used) == 2
    assert len(set(voices_used)) == 2  # Host and Guest get different voices


def test_cli_empty_input_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_read_input", lambda args: "")
    assert cli.main([]) == 2


def test_cli_setup_piper_downloads_selected_language(tmp_path, monkeypatch, capsys):
    model = tmp_path / "en_US-lessac-medium.onnx"
    model.write_bytes(b"model")
    seen = {}

    def fake_install(lang):
        seen["lang"] = lang
        return model

    monkeypatch.setattr(cli, "install_piper_voice", fake_install)

    assert cli.main(["--setup-piper", "--english"]) == 0
    assert seen["lang"] == "en"
    assert capsys.readouterr().out.strip() == str(model.resolve())


def test_cli_sensitive_edge_exits_3(tmp_path, capsys):
    rc = cli.main(["the password: hunter2", "--provider", "edge", "--out-dir", str(tmp_path)])
    assert rc == 3


@pytest.mark.parametrize("bad_rate", ["abc", "10%", "+10.5%"])
def test_cli_invalid_rate_does_not_fall_back(tmp_path, capsys, bad_rate):
    rc = cli.main(["Hello.", "--rate", bad_rate, "--out-dir", str(tmp_path)])
    assert rc == 3
    assert "invalid speech rate" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.mp3"))


def test_to_primitives_rounds_only_sync_timestamps():
    value = {
        "duration_s": 3.2519,
        "sync": engine.SyncTrack(
            (engine.TimedSegment("cue", 0.123456, 1.23456, 0),),
            source="edge-sentence-boundary",
        ),
        "formula": {"coefficient": 1.23456},
    }

    assert cli._to_primitives(value) == {
        "duration_s": 3.2519,
        "sync": {
            "segments": [{
                "text": "cue",
                "start_s": 0.123,
                "end_s": 1.235,
                "part_index": 0,
                "speaker": None,
            }],
            "granularity": "sentence",
            "source": "edge-sentence-boundary",
            "timebase": "media_seconds",
        },
        "formula": {"coefficient": 1.23456},
    }


def test_cli_writes_serialized_sync_formula_metadata_and_relative_library_link(tmp_path, monkeypatch, capsys):
    captured = {}
    audio_path = tmp_path / "metadata.mp3"
    transcript_path = tmp_path / "metadata.md"
    audio_path.write_bytes(b"fake audio")
    transcript_path.write_text("# Metadata\n\nThe formula is $x^2$.", encoding="utf-8")

    def fake_synth(text, **kwargs):
        captured["text"] = text
        captured.update(kwargs)
        return engine.SynthResult(
            audio_path=audio_path,
            transcript_path=transcript_path,
            provider="edge",
            provider_reason="fake",
            duration_s=3.25,
            n_parts=1,
            sync=engine.SyncTrack(
                (engine.TimedSegment("x squared.", 0.123456, 1.23456, 0),),
                source="edge-sentence-boundary",
            ),
            formulas=({
                "marker": "94778094778",
                "original": "$x^2$",
                "spoken": "x squared",
                "mathml": "<math><msup>x</msup></math>",
                "coefficient": 1.23456,
            },),
        )

    monkeypatch.setattr(cli.engine, "synth_monologue", fake_synth)
    rc = cli.main([
        "The formula is $x^2$.", "--lang", "en", "--tag", "math", "--tag", "daily",
        "--date", "2026-07-10", "--project", "AudioExplainer", "--out-dir", str(tmp_path),
    ])

    assert rc == 0
    assert captured["lang"] == "en"
    stdout = capsys.readouterr().out.strip().splitlines()
    assert stdout[-1] == str(audio_path)

    sidecar = json.loads((tmp_path / "metadata.audio.json").read_text(encoding="utf-8"))
    assert sidecar["schema_version"] == 1
    assert sidecar["created_at"]
    assert sidecar["content_date"] == "2026-07-10"
    assert sidecar["project"] == "AudioExplainer"
    assert sidecar["tags"] == ["math", "daily"]
    assert sidecar["sync"]["segments"][0]["start_s"] == 0.123
    assert sidecar["sync"]["segments"][0]["end_s"] == 1.235
    assert sidecar["duration_s"] == 3.25
    assert sidecar["formulas"][0]["coefficient"] == 1.23456
    assert sidecar["formulas"][0]["spoken"] == "x squared"
    assert "$x^2$" in sidecar["search_text"]
    assert "x squared" in sidecar["formula_text"]
    assert "The formula" in sidecar["transcript_text"]

    player = (tmp_path / "metadata.player.html").read_text(encoding="utf-8")
    assert '"library_link": "audio-library.html"' in player
    assert '"content_date"' not in player  # player API calls this field date
    assert "2026-07-10" in player
    assert "x squared" in player
    assert (tmp_path / "audio-library.html").exists()


def test_cli_library_failure_keeps_audio_contract(tmp_path, fake_provider, monkeypatch, capsys):
    def fail_rebuild(_directory):
        raise RuntimeError("library is locked")

    monkeypatch.setattr(cli.library, "rebuild_library", fail_rebuild)
    rc = cli.main(["Hello.", "--out-dir", str(tmp_path), "--title", "library failure"])
    captured = capsys.readouterr()

    assert rc == 0
    final_path = Path(captured.out.strip().splitlines()[-1])
    assert final_path.exists()
    assert "library rebuild unavailable" in captured.err


def test_cli_reports_rejected_edge_sync(tmp_path, monkeypatch, capsys):
    audio_path = tmp_path / "untimed-edge.mp3"
    transcript_path = tmp_path / "untimed-edge.md"
    audio_path.write_bytes(b"fake audio")
    transcript_path.write_text("No timing.", encoding="utf-8")

    monkeypatch.setattr(
        cli.engine,
        "synth_monologue",
        lambda text, **kwargs: engine.SynthResult(
            audio_path=audio_path,
            transcript_path=transcript_path,
            provider="edge",
            provider_reason="fake",
            duration_s=1.0,
            n_parts=1,
            sync=None,
        ),
    )

    assert cli.main(["No timing.", "--out-dir", str(tmp_path)]) == 0
    assert "sync: unavailable" in capsys.readouterr().err
