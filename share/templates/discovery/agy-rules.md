# Audio Explainer global rule

When the user asks for an audio explanation, summary, narration, podcast, or
read-aloud:

1. Write an audio-first script from the available context. `audioexplain` only
   synthesizes audio; it does not write or summarize.
2. Choose monologue or `--style dialogue` with short `Host:` / `Guest:` turns.
3. Synthesize into an explicit output directory:

   ```bash
   printf '%s' "$SCRIPT" | audioexplain --title "<short title>" --out-dir deliverables
   audioexplain --style dialogue --input script.md --out-dir deliverables
   ```

4. Report the absolute MP3 and `.player.html` paths printed by the tool.

Add `--english` for English. Use `--provider piper` for local neural speech or
`--provider say` for the local macOS system voice. The default `auto` chain is
Edge, Piper, then the system voice. Edge is online and sends narration text to
Microsoft.

Write for the ear: use short sentences, summarize code and long paths instead of
reading them literally, and structure the script as hook → two or three ideas →
recap. See `audio-first-contract.md` for the shared contract.
