"""Dependency diagnostics for `audioexplain --doctor`."""

from __future__ import annotations

import importlib.metadata
import shutil
import socket
import subprocess
from dataclasses import dataclass

from .providers import piper_data_dir, piper_model_path_for_lang


EDGE_PROBE_HOST = "speech.platform.bing.com"
EDGE_PROBE_PORT = 443


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""
    required: bool = False


def _dist_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _cmd_path(name: str) -> str | None:
    return shutil.which(name)


def _first_line(cmd: list[str], timeout: float = 2.0) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (proc.stdout or proc.stderr).strip()
    return text.splitlines()[0] if text else None


def _tcp_probe(host: str = EDGE_PROBE_HOST, port: int = EDGE_PROBE_PORT, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def collect_checks(probe_network: bool = True) -> list[Check]:
    """Return dependency checks without printing.

    `probe_network=False` is intended for unit tests and offline diagnostics.
    """
    edge_version = _dist_version("edge-tts")
    piper_version = _dist_version("piper-tts")
    piper_es_model = piper_model_path_for_lang("es")
    piper_en_model = piper_model_path_for_lang("en")
    piper_es_ready = (
        piper_es_model.exists()
        and piper_es_model.with_suffix(".onnx.json").exists()
    )
    piper_en_ready = (
        piper_en_model.exists()
        and piper_en_model.with_suffix(".onnx.json").exists()
    )
    ffmpeg = _cmd_path("ffmpeg")
    ffprobe = _cmd_path("ffprobe")
    say = _cmd_path("say")
    afplay = _cmd_path("afplay")
    network = _tcp_probe() if probe_network else False

    ffmpeg_version = _first_line([ffmpeg, "-version"]) if ffmpeg else None
    ffprobe_version = _first_line([ffprobe, "-version"]) if ffprobe else None

    return [
        Check(
            "edge-tts package",
            edge_version is not None,
            f"version {edge_version}" if edge_version else "not installed",
            "install with: uv tool install .",
        ),
        Check(
            "edge network probe",
            network,
            f"{EDGE_PROBE_HOST}:{EDGE_PROBE_PORT}" if network else "unreachable or blocked",
            "use --provider piper/say offline, or run with network access",
        ),
        Check(
            "Piper package",
            piper_version is not None,
            f"version {piper_version}" if piper_version else "not installed",
            "install this project with the optional 'piper' extra",
        ),
        Check(
            "Piper Spanish voice",
            piper_es_ready,
            str(piper_es_model) if piper_es_ready else f"not found in {piper_data_dir()}",
            "run: audioexplain --setup-piper",
        ),
        Check(
            "Piper English voice",
            piper_en_ready,
            str(piper_en_model) if piper_en_ready else f"not found in {piper_data_dir()}",
            "run: audioexplain --setup-piper --english",
        ),
        Check(
            "ffmpeg",
            ffmpeg is not None,
            ffmpeg_version or (ffmpeg or "not found"),
            "install with: brew install ffmpeg",
            required=True,
        ),
        Check(
            "ffprobe",
            ffprobe is not None,
            ffprobe_version or (ffprobe or "not found"),
            "ships with ffmpeg; duration will be unknown without it",
        ),
        Check(
            "macOS say",
            say is not None,
            say or "not found",
            "macOS offline fallback only",
        ),
        Check(
            "macOS afplay",
            afplay is not None,
            afplay or "not found",
            "optional; needed only for --play",
        ),
    ]


def _get(checks: list[Check], name: str) -> Check:
    return next(c for c in checks if c.name == name)


def doctor_ready(checks: list[Check]) -> tuple[bool, str]:
    """Return whether the default install can synthesize and assemble audio."""
    ffmpeg_ok = _get(checks, "ffmpeg").ok
    edge_ok = _get(checks, "edge-tts package").ok and _get(checks, "edge network probe").ok
    piper_voice_ok = (
        _get(checks, "Piper Spanish voice").ok
        or _get(checks, "Piper English voice").ok
    )
    piper_ok = _get(checks, "Piper package").ok and piper_voice_ok
    say_ok = _get(checks, "macOS say").ok

    if ffmpeg_ok and edge_ok:
        neural_fallback = "available" if piper_ok else "unavailable"
        system_fallback = "available" if say_ok else "unavailable"
        return True, (
            "edge neural path available; local neural Piper fallback "
            f"{neural_fallback}; system fallback {system_fallback}"
        )
    if ffmpeg_ok and piper_ok:
        return True, "local neural Piper path available; edge neural path unavailable"
    if ffmpeg_ok and say_ok:
        return True, "offline system voice available; neural paths unavailable"
    if not ffmpeg_ok:
        return False, "ffmpeg is required for concat and say-to-mp3 conversion"
    return False, "need Edge with network, local Piper, or a system voice fallback"


def run_doctor(probe_network: bool = True) -> int:
    checks = collect_checks(probe_network=probe_network)
    for check in checks:
        mark = " OK " if check.ok else "MISS"
        label = check.name
        if check.required:
            label += " (required)"
        line = f"[{mark}] {label}: {check.detail}"
        if not check.ok and check.hint:
            line += f"  -> {check.hint}"
        print(line)

    ready, reason = doctor_ready(checks)
    print()
    print("provider policy: auto = Edge, then local neural Piper, then the system voice")
    if ready:
        print(f"audioexplain: OK - {reason}.")
        return 0
    print(f"audioexplain: NOT READY - {reason}.")
    return 1
