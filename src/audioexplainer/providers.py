"""TTS providers: Edge (online), Piper (local neural), and macOS ``say``.

Each provider exposes:
    available() -> bool
    synth(text, out_path, voice, rate) -> ProviderSynthesis

Timing is captured here, at the provider boundary.  The rest of the package
only deals in media seconds and does not need to know Edge's tick timebase.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce audio (deps, network, bad voice)."""


@dataclass(frozen=True)
class SpeechBoundary:
    """A provider-neutral spoken cue on the audio timeline, in seconds."""

    text: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class ProviderSynthesis:
    """Audio emitted by one provider request and optional speech boundaries."""

    audio_path: Path
    boundaries: tuple[SpeechBoundary, ...] | None = None


class EdgeProvider:
    name = "edge"

    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
        except Exception:
            return False
        return True

    def synth(
        self, text: str, out_path: Path, voice: str, rate: str = "-8%"
    ) -> ProviderSynthesis:
        try:
            import edge_tts
        except Exception as e:  # pragma: no cover - import guard
            raise ProviderError(
                "edge-tts not installed; install it or use --provider piper/say"
            ) from e

        out_path.parent.mkdir(parents=True, exist_ok=True)

        async def _run() -> tuple[SpeechBoundary, ...]:
            # ``stream`` is required for SentenceBoundary events; ``save`` only
            # writes audio and discards timing metadata.
            communicate = edge_tts.Communicate(
                text, voice=voice, rate=rate, boundary="SentenceBoundary"
            )
            boundaries: list[SpeechBoundary] = []
            with out_path.open("wb") as audio_file:
                async for event in communicate.stream():
                    if event.get("type") == "audio":
                        audio_file.write(event["data"])
                    elif event.get("type") == "SentenceBoundary":
                        boundaries.append(_edge_boundary(event))
            return tuple(boundaries)

        try:
            boundaries = asyncio.run(_run())
        except Exception as e:
            raise ProviderError(
                f"edge-tts synthesis failed (network or voice '{voice}'?): {e}"
            ) from e
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise ProviderError("edge-tts produced no audio (likely no network)")
        return ProviderSynthesis(out_path, boundaries)


PIPER_DEFAULT_MODELS = {
    "es": "es_MX-ald-medium",
    "en": "en_US-lessac-medium",
}
PIPER_SYNTH_TIMEOUT_S = 180
PIPER_DOWNLOAD_TIMEOUT_S = 600


def piper_data_dir() -> Path:
    """Return the configurable directory containing local Piper voice files."""
    configured = os.environ.get("AUDIOEXPLAINER_PIPER_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "audioexplainer" / "piper"


def piper_model_name_for_lang(lang: str) -> str:
    lang = "en" if lang.lower().startswith("en") else "es"
    return os.environ.get(
        f"AUDIOEXPLAINER_PIPER_MODEL_{lang.upper()}",
        PIPER_DEFAULT_MODELS[lang],
    )


def piper_model_path_for_lang(lang: str) -> Path:
    """Resolve the configured Piper model for a language."""
    configured = Path(piper_model_name_for_lang(lang)).expanduser()
    if configured.suffix == ".onnx" or configured.is_absolute():
        return configured
    return piper_data_dir() / f"{configured}.onnx"


def piper_model_path(voice: str) -> Path:
    """Resolve a Piper model for an Edge-style voice id."""
    lang = "en" if voice.lower().startswith("en") else "es"
    return piper_model_path_for_lang(lang)


def _piper_installed() -> bool:
    try:
        return importlib.util.find_spec("piper") is not None
    except (ImportError, ValueError):
        return False


def rate_multiplier(rate: str) -> float:
    """Validate a percentage speech rate and return its speed multiplier."""
    raw = rate.strip()
    if re.fullmatch(r"[+-]\d+%", raw) is None:
        raise ProviderError(
            f"invalid speech rate {rate!r}; expected a signed integer percentage such as +10%"
        )
    speed = 1.0 + int(raw[:-1]) / 100.0
    if not 0.25 <= speed <= 4.0:
        raise ProviderError(f"speech rate {rate!r} is outside the supported range")
    return speed


def _piper_rate_scale(rate: str) -> float:
    """Translate an Edge percentage rate into Piper's inverse length scale."""
    return 1.0 / rate_multiplier(rate)


class PiperProvider:
    """Local neural TTS through Piper's CLI.

    Piper is invoked as a separate optional program instead of imported into
    the application. This keeps model loading isolated and makes the optional
    GPL-licensed runtime boundary explicit.
    """

    name = "piper"

    def available(self) -> bool:
        if not _piper_installed():
            return False
        return any(
            piper_model_path_for_lang(lang).exists()
            and piper_model_path_for_lang(lang).with_suffix(".onnx.json").exists()
            for lang in PIPER_DEFAULT_MODELS
        )

    def available_for(self, voice: str) -> bool:
        model = piper_model_path(voice)
        return (
            _piper_installed()
            and model.exists()
            and model.with_suffix(".onnx.json").exists()
        )

    def synth(
        self, text: str, out_path: Path, voice: str, rate: str = "-8%"
    ) -> ProviderSynthesis:
        if not _piper_installed():
            raise ProviderError(
                "Piper is not installed; install AudioExplainer with the 'piper' extra"
            )
        if shutil.which("ffmpeg") is None:
            raise ProviderError("ffmpeg is required to convert Piper WAV output to mp3")

        model = piper_model_path(voice)
        config = model.with_suffix(".onnx.json")
        if not model.exists() or not config.exists():
            lang = "en" if voice.lower().startswith("en") else "es"
            raise ProviderError(
                f"Piper {lang} voice is not installed; run `audioexplain --setup-piper --lang {lang}`"
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="audioexplainer-piper-") as td:
            tmp = Path(td)
            input_path = tmp / "input.txt"
            wav_path = tmp / "speech.wav"
            input_path.write_text(text, encoding="utf-8")
            command = [
                sys.executable,
                "-m",
                "piper",
                "--model",
                str(model),
                "--config",
                str(config),
                "--input-file",
                str(input_path),
                "--output-file",
                str(wav_path),
                "--length-scale",
                f"{_piper_rate_scale(rate):.6f}",
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=PIPER_SYNTH_TIMEOUT_S,
                )
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(wav_path), str(out_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=PIPER_SYNTH_TIMEOUT_S,
                )
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                OSError,
            ) as e:
                detail = (
                    getattr(e, "stderr", None)
                    or getattr(e, "stdout", None)
                    or str(e)
                ).strip()
                raise ProviderError(f"Piper synthesis failed: {detail}") from e

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise ProviderError("Piper produced no audio")
        # Piper's CLI does not expose stable sentence timestamps. Audio remains
        # valid; the engine can derive labelled estimated tracking from duration.
        return ProviderSynthesis(out_path, None)


def install_piper_voice(lang: str = "es") -> Path:
    """Download AudioExplainer's default Piper model for one language."""
    normalized = "en" if lang.lower().startswith("en") else "es"
    if not _piper_installed():
        raise ProviderError(
            "Piper is not installed; run `uv tool install '.[piper]'` from the project"
        )
    target = piper_data_dir()
    target.mkdir(parents=True, exist_ok=True)
    model_name = PIPER_DEFAULT_MODELS[normalized]
    command = [
        sys.executable,
        "-m",
        "piper.download_voices",
        "--data-dir",
        str(target),
        model_name,
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=sys.stderr,
            stderr=sys.stderr,
            text=True,
            timeout=PIPER_DOWNLOAD_TIMEOUT_S,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
        ValueError,
    ) as e:
        detail = (
            getattr(e, "stderr", None)
            or getattr(e, "stdout", None)
            or str(e)
        ).strip()
        raise ProviderError(f"Piper voice download failed: {detail}") from e
    model = target / f"{model_name}.onnx"
    if not model.exists() or not model.with_suffix(".onnx.json").exists():
        raise ProviderError(f"Piper download finished but model files are missing in {target}")
    return model


class SayProvider:
    name = "say"

    def available(self) -> bool:
        return shutil.which("say") is not None

    def synth(
        self, text: str, out_path: Path, voice: str = "Paulina", rate: int = 180
    ) -> ProviderSynthesis:
        if shutil.which("say") is None:
            raise ProviderError("macOS `say` not available (offline provider is macOS-only)")
        if shutil.which("ffmpeg") is None:
            raise ProviderError("ffmpeg required to convert `say` output to mp3")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        aiff = out_path.with_suffix(".aiff")
        # Write text to a temp file to avoid arg-length / quoting issues.
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(text)
            txt_path = tf.name
        try:
            subprocess.run(
                ["say", "-v", voice, "-r", str(rate), "-f", txt_path, "-o", str(aiff)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(aiff), str(out_path)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", "ignore") if e.stderr else ""
            raise ProviderError(f"`say` synthesis failed: {stderr or e}") from e
        finally:
            Path(txt_path).unlink(missing_ok=True)
            aiff.unlink(missing_ok=True)
        # macOS say exposes no native sentence timing. The engine derives and
        # labels duration-weighted tracking after synthesis.
        return ProviderSynthesis(out_path, None)


def _edge_boundary(event: dict) -> SpeechBoundary:
    """Translate an Edge stream event's 100-nanosecond ticks to seconds."""
    try:
        offset = event["offset"]
        duration = event["duration"]
        text = event["text"]
    except KeyError as e:
        raise ProviderError(f"edge-tts emitted an incomplete SentenceBoundary: {event!r}") from e
    if not isinstance(text, str):
        raise ProviderError("edge-tts emitted a SentenceBoundary without text")
    try:
        start_s = float(offset) / 10_000_000
        end_s = (float(offset) + float(duration)) / 10_000_000
        return SpeechBoundary(text, start_s, end_s)
    except (TypeError, ValueError) as e:
        raise ProviderError(f"edge-tts emitted invalid SentenceBoundary ticks: {event!r}") from e
