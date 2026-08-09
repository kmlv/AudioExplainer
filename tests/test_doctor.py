from __future__ import annotations

from audioexplainer import doctor


def _checks(
    edge=True,
    network=True,
    piper=False,
    piper_voice=False,
    piper_en_voice=False,
    ffmpeg=True,
    ffprobe=True,
    say=True,
    afplay=False,
):
    return [
        doctor.Check("edge-tts package", edge, "version 6.1"),
        doctor.Check("edge network probe", network, "ok"),
        doctor.Check("Piper package", piper, "version 1.4.2"),
        doctor.Check("Piper Spanish voice", piper_voice, "model"),
        doctor.Check("Piper English voice", piper_en_voice, "model"),
        doctor.Check("ffmpeg", ffmpeg, "ffmpeg version", required=True),
        doctor.Check("ffprobe", ffprobe, "ffprobe version"),
        doctor.Check("macOS say", say, "/usr/bin/say"),
        doctor.Check("macOS afplay", afplay, "not found"),
    ]


def test_doctor_ready_with_edge_and_network():
    ready, reason = doctor.doctor_ready(_checks(edge=True, network=True, ffmpeg=True, say=False))
    assert ready
    assert "edge neural path" in reason


def test_doctor_ready_with_offline_say_when_edge_unavailable():
    ready, reason = doctor.doctor_ready(_checks(edge=False, network=False, ffmpeg=True, say=True))
    assert ready
    assert "offline system voice" in reason


def test_doctor_ready_with_local_neural_piper_only():
    ready, reason = doctor.doctor_ready(
        _checks(
            edge=False,
            network=False,
            piper=True,
            piper_voice=True,
            say=False,
        )
    )
    assert ready
    assert "local neural Piper path" in reason


def test_doctor_ready_with_only_english_piper_voice():
    ready, reason = doctor.doctor_ready(
        _checks(
            edge=False,
            network=False,
            piper=True,
            piper_voice=False,
            piper_en_voice=True,
            say=False,
        )
    )
    assert ready
    assert "local neural Piper path" in reason


def test_doctor_not_ready_without_ffmpeg():
    ready, reason = doctor.doctor_ready(_checks(edge=True, network=True, ffmpeg=False, say=True))
    assert not ready
    assert "ffmpeg" in reason


def test_run_doctor_reports_not_ready(monkeypatch, capsys):
    monkeypatch.setattr(
        doctor,
        "collect_checks",
        lambda probe_network=True: _checks(edge=False, network=False, ffmpeg=False, say=False),
    )
    assert doctor.run_doctor() == 1
    out = capsys.readouterr().out
    assert "NOT READY" in out
    assert "ffmpeg" in out
