---
name: audio-explainer
description: Use when the user asks for an audio explanation, audio summary, narration, podcast, read-aloud, or an MP3 to listen to. Write an audio-first script from the available context, then synthesize it with the audioexplain CLI.
---

# Audio Explainer

Write the explanation from the repository, document, diff, or prompt context.
The `audioexplain` CLI only converts the prepared script into audio.

## Workflow

1. Determine what the listener needs to understand.
2. Write short, active sentences with a hook, two or three ideas, and a recap.
   Summarize raw code, file paths, URLs, secrets, and stack traces.
3. Choose monologue or two-speaker dialogue using `Host:` and `Guest:` lines.
4. Synthesize into an explicit output directory and report the absolute MP3 and
   player paths printed by the command.

```bash
printf '%s' "$SCRIPT" | audioexplain --title "<short title>" --out-dir deliverables
audioexplain --style dialogue --input script.md --title "<short title>" --out-dir deliverables
```

Add `--english` for English. Use `--provider piper` for local neural synthesis
or `--provider say` for the local macOS system voice. The default `auto` chain is
Edge, Piper, then the system voice. Edge synthesis is online and sends narration
text to Microsoft. Run `audioexplain --doctor` to diagnose the installation.

The generated `.player.html` supports playback, seeking, 0.05x speed changes,
Markdown rendering, and transcript following. If `file://` is unavailable,
serve the output folder with `python3 -m http.server 8765 --bind 127.0.0.1`.
