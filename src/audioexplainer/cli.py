"""audioexplain CLI and its cross-provider input/output contract.

Contract:
  - input from stdin (default), --input FILE, or positional args
  - writes an MP3 + a .md transcript + a local .player.html browser player
  - the FINAL stdout line is the MP3 path (so the host AI can capture/report it)
  - human-readable progress goes to STDERR (never pollutes the stdout contract)
  - exit 3 on sensitive-content refusal / provider/network failure
  - exit 2 on bad/empty input

The HOST AI writes the script; this tool only synthesizes audio.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from . import doctor, engine, voices
from . import library
from .player import write_player
from .providers import ProviderError, install_piper_voice


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audioexplain",
        description="Turn an (AI-written) explainer script into a neural-voice MP3.",
    )
    p.add_argument("text", nargs="*", help="script text (else read --input or stdin)")
    p.add_argument("--input", type=str, help="read the script from a file")
    p.add_argument("--style", choices=["mono", "dialogue"], default="mono",
                   help="mono = one narrator; dialogue = two-voice 'podcast' (Host:/Guest: lines)")
    p.add_argument("--voice", default="", help="voice id or alias (mono narrator / dialogue voice A)")
    p.add_argument("--voice-b", default="", help="dialogue voice B")
    p.add_argument("--english", action="store_true", help="use English defaults")
    p.add_argument("--lang", choices=["es", "en"], default="",
                   help="es|en (selects dialogue voice pair)")
    p.add_argument("--rate", default=engine.DEFAULT_RATE, help="edge speech rate, e.g. -8%% or +5%%")
    p.add_argument("--title", default="audio explainer", help="title (used in filename + transcript)")
    p.add_argument("--out", type=str, help="explicit output mp3 path")
    p.add_argument("--out-dir", type=str, help="output dir (default: /tmp/audioexplainer)")
    p.add_argument("--tag", action="append", default=[], help="repeatable searchable tag")
    p.add_argument(
        "--date", "--content-date", dest="content_date", default=None,
        help="optional content date (kept separate from automatic created_at)",
    )
    p.add_argument("--project", default=None, help="optional project label stored in metadata")
    p.add_argument("--provider", choices=["auto", "edge", "piper", "say"], default="auto",
                   help="auto: Edge, then local neural Piper, then the system voice")
    p.add_argument(
        "--setup-piper",
        action="store_true",
        help="download the default local neural voice for --lang (Spanish by default)",
    )
    p.add_argument("--allow-sensitive", action="store_true",
                   help="bypass the local sensitive-content refusal (never bypasses provider disclosure)")
    p.add_argument("--play", action="store_true", help="play the result when done (macOS afplay)")
    p.add_argument("--list-voices", action="store_true", help="print recommended voices and exit")
    p.add_argument("--doctor", action="store_true", help="check dependencies and exit")
    return p


def _read_input(args: argparse.Namespace) -> str:
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    if args.text:
        return " ".join(args.text)
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


_SYNC_TIMESTAMP_FIELDS = frozenset({"start_s", "end_s"})


def _to_primitives(value, *, field_name: str | None = None):
    """Convert engine records into JSON-safe primitives.

    Provider boundary times are represented in seconds, but their source
    tick-to-second conversion can leave insignificant binary noise.  Round
    only the explicitly named sync timestamp fields; durations and formula
    values are independent data and must retain their original precision.
    """
    if dataclasses.is_dataclass(value):
        return {
            field.name: _to_primitives(
                getattr(value, field.name), field_name=field.name
            )
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _to_primitives(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_to_primitives(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if field_name in _SYNC_TIMESTAMP_FIELDS:
            return round(value, 3)
        return value
    return str(value)


def _formula_search_text(formulas: list[dict]) -> str:
    terms: list[str] = []
    for formula in formulas:
        if not isinstance(formula, Mapping):
            continue
        for key in ("original", "spoken", "latex", "text"):
            value = formula.get(key)
            if value:
                terms.append(str(value))
    return " ".join(terms)


def _enrich_sidecar(
    sidecar_path: Path,
    *,
    title: str,
    transcript_path: Path,
    formulas: list[dict],
    tags: list[str],
    content_date: str | None,
    project: str | None,
) -> None:
    """Add integration metadata while retaining library.py's schema/API."""
    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    transcript_text = transcript_path.read_text(encoding="utf-8")
    formula_text = _formula_search_text(formulas)
    searchable = " ".join(
        value for value in (
            title,
            " ".join(tags),
            content_date or "",
            project or "",
            transcript_text,
            formula_text,
        ) if value
    )
    data.update({
        "formulas": formulas,
        "transcript_text": transcript_text,
        "formula_text": formula_text,
        "search_text": searchable,
    })
    if content_date is not None:
        data["content_date"] = content_date
    else:
        data.pop("content_date", None)
    if project is not None:
        data["project"] = project
    else:
        data.pop("project", None)

    tmp_path = sidecar_path.with_name(f".{sidecar_path.name}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(tmp_path, sidecar_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.doctor:
        return doctor.run_doctor()
    if args.setup_piper:
        lang = args.lang or ("en" if args.english else "es")
        print(
            f"[audioexplain] downloading the local Piper {lang} voice...",
            file=sys.stderr,
        )
        try:
            model = install_piper_voice(lang)
        except ProviderError as e:
            print(f"error: {e}", file=sys.stderr)
            return 3
        print(f"[audioexplain] Piper voice ready: {model}", file=sys.stderr)
        print(model.resolve())
        return 0
    if args.list_voices:
        for v in voices.RECOMMENDED:
            print(v)
        return 0

    lang = args.lang or ("en" if args.english else "es")
    default_voice = (
        voices.DEFAULT_EDGE_VOICE_EN if (args.english or lang == "en")
        else voices.DEFAULT_EDGE_VOICE_ES
    )

    try:
        text = _read_input(args)
        if not text.strip():
            print("error: no input (pass text, --input FILE, or pipe via stdin)", file=sys.stderr)
            return 2
        if args.style == "dialogue":
            res = engine.synth_dialogue(
                text,
                voice_a=args.voice or None,
                voice_b=args.voice_b or None,
                lang=lang,
                rate=args.rate,
                provider=args.provider,
                out_path=args.out,
                out_dir=args.out_dir,
                title=args.title,
                allow_sensitive=args.allow_sensitive,
            )
        else:
            res = engine.synth_monologue(
                text,
                voice=args.voice or default_voice,
                rate=args.rate,
                lang=lang,
                provider=args.provider,
                out_path=args.out,
                out_dir=args.out_dir,
                title=args.title,
                allow_sensitive=args.allow_sensitive,
            )
    except ProviderError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    dur = f"{res.duration_s:.0f}s" if res.duration_s else "unknown"
    print(
        f"[audioexplain] provider={res.provider} ({res.provider_reason}) "
        f"parts={res.n_parts} duration={dur}",
        file=sys.stderr,
    )
    # Absolute paths so the file is always findable (reported clearly on stderr).
    audio_path = Path(res.audio_path).expanduser().resolve()
    transcript_path = Path(res.transcript_path).expanduser().resolve()
    print(f"[audioexplain] SAVED (absolute): {audio_path}", file=sys.stderr)
    print(f"[audioexplain] transcript: {transcript_path}", file=sys.stderr)

    # The player and library are companion artifacts.  Their failures must not
    # change the audio contract: the final stdout line remains the MP3 path.
    output_dir = audio_path.parent
    library_path = output_dir / "audio-library.html"
    sync_data = _to_primitives(res.sync) if res.sync is not None else None
    if res.sync is None:
        print(
            "[audioexplain] sync: unavailable "
            "(audio duration unavailable for transcript alignment)",
            file=sys.stderr,
        )
    formula_data = [_to_primitives(formula) for formula in (res.formulas or ())]
    player_path = audio_path.with_suffix(".player.html")
    try:
        player_path = write_player(
            audio_path,
            title=args.title,
            transcript_path=transcript_path,
            duration_s=res.duration_s,
            sync=sync_data,
            formulas=formula_data,
            tags=list(args.tag),
            date=args.content_date,
            library_link=os.path.relpath(library_path, output_dir),
            lang=lang,
        )
        print(f"[audioexplain] player: {player_path}", file=sys.stderr)
    except Exception as e:
        print(f"[audioexplain] warning: player artifact unavailable: {e}", file=sys.stderr)

    sidecar_path = None
    try:
        # library.py owns schema_version/created_at and preserves unknown
        # duration as JSON null rather than presenting a false zero-second clip.
        sidecar_path = Path(library.write_sidecar(
            audio_path,
            title=args.title,
            provider=res.provider,
            duration_s=res.duration_s,
            transcript_path=transcript_path,
            player_path=player_path if player_path.exists() else None,
            sync=sync_data,
            tags=list(args.tag),
        ))
        _enrich_sidecar(
            sidecar_path,
            title=args.title,
            transcript_path=transcript_path,
            formulas=formula_data,
            tags=list(args.tag),
            content_date=args.content_date,
            project=args.project,
        )
        print(f"[audioexplain] sidecar: {sidecar_path}", file=sys.stderr)
    except Exception as e:
        print(f"[audioexplain] warning: sidecar unavailable: {e}", file=sys.stderr)

    try:
        library.rebuild_library(output_dir)
        generated_library = output_dir / "audio-library.html"
        if generated_library.exists() and "<!-- GENERATOR: AUDIOEXPLAINER -->" in generated_library.read_text(encoding="utf-8"):
            print(f"[audioexplain] library: {generated_library}", file=sys.stderr)
    except Exception as e:
        print(f"[audioexplain] warning: library rebuild unavailable: {e}", file=sys.stderr)

    if args.play and shutil.which("afplay"):
        subprocess.Popen(["afplay", str(audio_path)])

    # CONTRACT: final stdout line is the absolute MP3 path.
    print(audio_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
