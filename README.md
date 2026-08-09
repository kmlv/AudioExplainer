# AudioExplainer

AudioExplainer turns a prepared script into a neural-voice MP3, a Markdown
transcript, and a dependency-free browser player. It is designed for AI agents,
developer tools, and command-line workflows that already have the context needed
to write the explanation.

The host application writes the script. AudioExplainer only preprocesses and
synthesizes it; it does not call a language model.

> **Project status:** alpha. Interfaces and generated metadata may change before
> a stable release.

## Features

- Spanish and English monologues or two-speaker dialogue
- online neural speech through `edge-tts`
- optional local neural fallback through Piper
- local system-voice fallback on macOS
- automatic provider fallback: Edge → Piper → system voice
- Markdown-aware narration, including headings, emphasis, and formulas
- synchronized transcript for every provider: exact Edge boundaries when
  available and clearly labelled duration-based alignment for local voices
- accessible local player with seeking, transcript following, and playback speed
  adjustments in 0.05x steps
- per-directory audio library and versioned metadata sidecars

## Install

Install the standard package:

```bash
uv tool install .
```

To add the local neural fallback:

```bash
uv tool install '.[piper]'
audioexplain --setup-piper
```

Audio conversion and duration detection require `ffmpeg` and `ffprobe`. Run the
health check after installation:

```bash
audioexplain --doctor
```

Piper is an optional, separately distributed GPL-licensed runtime. Downloaded
voice models retain their own licenses.

## Use

Create a Spanish monologue from standard input:

```bash
printf '%s' "Aquí tienes un resumen breve del cambio." | \
  audioexplain --title "resumen" --out-dir deliverables
```

Read a Markdown file in English:

```bash
audioexplain --input script.md --english \
  --title "daily recap" --out-dir deliverables
```

Create a two-voice explanation from `Host:` and `Guest:` lines:

```bash
audioexplain --style dialogue --input dialogue.md \
  --title "deep dive" --out-dir deliverables
```

Keep synthesis local with Piper:

```bash
audioexplain --provider piper --input private-notes.md
```

Each run prints the absolute MP3 path and writes the transcript, player, and
metadata next to it. The default output directory is temporary; pass an explicit
`--out-dir` when the artifacts should persist.

## Browser player

The generated `.player.html` works without a server or external assets. It
includes:

- play/pause and primary `-10` / `+10` second controls
- optional precise jumps of `-15`, `-5`, `+5`, and `+15` seconds
- a progress scrubber and elapsed/total time
- compact `− / speed / +` controls from 0.75x to 2x in exact 0.05x steps
- an article view and sentence-level view
- Markdown rendering and formula presentation
- current-sentence highlighting and optional automatic scrolling

Edge supplies exact sentence events when available. If those events are missing
or invalid, and for Piper and the macOS system voice which do not provide them,
AudioExplainer distributes the measured audio duration across sentences and
labels their tracking as approximate.

If a browser surface blocks local `file://` pages, serve the output directory:

```bash
cd deliverables
python3 -m http.server 8765 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8765/<file>.player.html`.

## Providers and privacy

For ordinary text, `--provider auto` tries Edge neural speech first, then local
Piper, then the macOS system voice. If the safety check detects an obvious
credential, automatic mode skips the online provider. Edge synthesis is an
online service and sends narration text to Microsoft. `edge-tts` is an
independent client and is not an official Azure Speech SDK; service availability
can change.

Use `--provider piper` or `--provider say` for material that must remain local.
AudioExplainer refuses obvious credentials with the online provider unless
`--allow-sensitive` is supplied explicitly.

## Agent discovery templates

Reusable discovery snippets live in `share/templates/discovery/`. They teach a
host agent to write an audio-first script, call `audioexplain`, and return the
absolute output paths. Review and copy a template into the relevant agent's
configuration only when you want that integration.

## Development

```bash
uv sync --extra dev
uv run pytest
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

## License

MIT. See [LICENSE](LICENSE).
