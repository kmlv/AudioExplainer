# Audio-first script contract

When the user asks for an audio explanation, the host application writes the
script and then hands it to `audioexplain`. The synthesizer does not summarize or
call a language model.

## Write for the ear

- Use short sentences, active voice, and a conversational tone.
- Summarize raw code, stack traces, file paths, and long URLs.
- Expand acronyms on first use.
- Use punctuation to create natural pacing.
- Default to a hook, two or three main ideas, and a brief recap.

## Dialogue mode

Use speaker-tagged lines and keep each turn under roughly 40 to 50 words:

```text
Host: Hoy revisamos el cambio principal del proyecto.
Guest: El resultado es una experiencia más clara y confiable.
Host: ¿Qué debería recordar quien escucha?
Guest: Que el flujo sigue siendo simple, pero ahora tiene mejores respaldos.
```

The first distinct speaker receives voice A and the second receives voice B.

## Synthesize and report

```bash
printf '%s' "$SCRIPT" | audioexplain --title "resumen" --out-dir deliverables
audioexplain --style dialogue --input script.md --title "conversación" --out-dir deliverables
```

Spanish is the default. Add `--english` for English. Always report the absolute
MP3 and `.player.html` paths printed by the command. Choose an explicit output
directory for persistent artifacts and the generated audio library.

Markdown formulas are verbalized and retained for visual rendering. Edge uses
exact provider sentence events; local voices use clearly labelled,
duration-based sentence tracking.

## Privacy

`--provider auto` uses Edge online neural speech, then local Piper, then the
macOS system voice. Edge sends narration text to Microsoft. Use
`--provider piper` or `--provider say` when text must remain local.
