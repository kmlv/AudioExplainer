---
name: audio-explainer
description: Use when the user asks for an audio explanation, audio summary, narration, podcast, read-aloud, or an MP3 to listen to. Write an audio-first script from the available context, then synthesize it with the audioexplain CLI.
---

# Audio Explainer

The user wants to listen to an explanation. Write the script from the available
context; `audioexplain` only synthesizes it.

## Workflow

1. Gather the context needed for an accurate explanation.
2. Write short, conversational sentences for the ear. Summarize code, paths,
   URLs, and stack traces rather than reading them literally.
3. Use monologue mode or short `Host:` / `Guest:` turns with `--style dialogue`.
4. Synthesize into an explicit output directory:

   ```bash
   printf '%s' "$SCRIPT" | audioexplain --title "<short title>" --out-dir deliverables
   audioexplain --style dialogue --input script.md --title "<short title>" --out-dir deliverables
   ```

5. Report the absolute MP3 and `.player.html` paths printed by the tool.

Use `--english` for English. For text that must remain local, use
`--provider piper` for neural speech or `--provider say` for the macOS system
voice. Edge synthesis is online and sends narration text to Microsoft. Run
`audioexplain --doctor` when dependencies need diagnosis.

The generated player supports playback, seeking, speed changes, Markdown, and
transcript following. If local pages are blocked, serve the output directory
with `python3 -m http.server 8765 --bind 127.0.0.1` and open the localhost URL.
