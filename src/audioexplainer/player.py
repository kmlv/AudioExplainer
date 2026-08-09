"""Static HTML player artifact for generated audio explainers."""

from __future__ import annotations

import json
import os
import tempfile
from html import escape
from pathlib import Path


def safe_json_dumps(obj):
    """Safely embed JSON in HTML <script> tags."""
    s = json.dumps(obj, ensure_ascii=False)
    s = s.replace('<', '\\u003c')
    s = s.replace('>', '\\u003e')
    s = s.replace('&', '\\u0026')
    s = s.replace('\u2028', '\\u2028')
    s = s.replace('\u2029', '\\u2029')
    return s


def write_player(
    audio_path: Path,
    *,
    title: str,
    transcript_path: Path | None = None,
    duration_s: float | None = None,
    sync: dict | None = None,
    tags: list[str] | None = None,
    formulas: list[dict] | None = None,
    library_link: str | None = None,
    date: str | None = None,
    lang: str = "es",
) -> Path:
    """Write a dependency-free browser player next to ``audio_path``."""
    audio_path = audio_path.resolve()
    transcript_path = transcript_path.resolve() if transcript_path else None
    player_path = audio_path.with_suffix(".player.html")
    audio_name = audio_path.name
    transcript_name = transcript_path.name if transcript_path else ""
    transcript_text = ""
    if transcript_path and transcript_path.exists():
        transcript_text = transcript_path.read_text(encoding="utf-8")

    language = "en" if lang.lower().startswith("en") else "es"
    ui = {
        "es": {
            "play": "Play", "pause": "Pausa", "follow": "Seguir",
            "article": "Artículo", "sentences": "Oraciones",
            "advanced": "Controles avanzados", "formulas": "Fórmulas",
            "untimed": "Sin tiempos; seguimiento no disponible",
            "estimated": "Seguimiento aproximado para esta voz",
            "loading": "Cargando audio...", "ready": "Audio listo",
            "audio_error": "No se pudo cargar el audio",
            "article_view": "Vista de artículo", "sentence_view": "Vista por oraciones",
            "speed": "Velocidad", "position": "Posición", "progress": "Progreso",
            "rewind": "Retroceder", "forward": "Avanzar", "seconds": "segundos",
            "transcript_view": "Vista del transcript", "transcript": "Transcripción", "transcript_link": "Guión",
            "skip_controls": "Saltar en el audio", "playback_speed": "Velocidad de reproducción",
            "quick_playback_speed": "Velocidades rápidas", "current_speed": "Velocidad actual",
            "normal_speed": "Velocidad normal", "reset_speed": "restablecer a 1x",
            "minimum_speed": "Velocidad mínima", "maximum_speed": "Velocidad máxima",
            "decrease_speed": "Reducir velocidad", "increase_speed": "Aumentar velocidad",
            "close": "Cerrar", "library": "Librería",
            "follow_paused": "Seguimiento pausado mientras te desplazas",
            "follow_disabled": "Seguimiento desactivado", "follow_resumed": "Seguimiento reanudado",
        },
        "en": {
            "play": "Play", "pause": "Pause", "follow": "Follow",
            "article": "Article", "sentences": "Sentences",
            "advanced": "Advanced controls", "formulas": "Formulas",
            "untimed": "No timing data; transcript follow is unavailable",
            "estimated": "Approximate transcript timing for this voice",
            "loading": "Loading audio...", "ready": "Audio ready",
            "audio_error": "Audio could not be loaded",
            "article_view": "Article view", "sentence_view": "Sentence view",
            "speed": "Speed", "position": "Position", "progress": "Progress",
            "rewind": "Rewind", "forward": "Forward", "seconds": "seconds",
            "transcript_view": "Transcript view", "transcript": "Transcript", "transcript_link": "Transcript",
            "skip_controls": "Skip through audio", "playback_speed": "Playback speed",
            "quick_playback_speed": "Quick playback speeds", "current_speed": "Current speed",
            "normal_speed": "Normal speed", "reset_speed": "reset to 1x",
            "minimum_speed": "Minimum speed", "maximum_speed": "Maximum speed",
            "decrease_speed": "Decrease speed", "increase_speed": "Increase speed",
            "close": "Close", "library": "Library",
            "follow_paused": "Follow paused while you scroll",
            "follow_disabled": "Follow turned off", "follow_resumed": "Follow resumed",
        },
    }[language]
    data = {
        "audio": audio_name,
        "title": title,
        "transcript": transcript_name,
        "transcriptText": transcript_text,
        "duration": duration_s,
        "sync": sync,
        "tags": tags or [],
        "formulas": formulas or [],
        "library_link": library_link,
        "date": date,
        "lang": language,
        "ui": ui,
    }

    before_data, marker, after_data = _HTML_TEMPLATE.partition("__PLAYER_DATA__")
    if not marker:
        raise RuntimeError("player template is missing its data marker")
    before_data = before_data.replace("__HTML_LANG__", language).replace("__TITLE__", escape(title))
    after_data = after_data.replace("__HTML_LANG__", language).replace("__TITLE__", escape(title))
    html = before_data + safe_json_dumps(data) + after_data
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=player_path.parent,
            prefix=f".{player_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(html)
        os.replace(tmp_path, player_path)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    return player_path


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="__HTML_LANG__">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>__TITLE__</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #111827;
      --muted: #5b6472;
      --line: #d8dee8;
      --accent: #155eef;
      --accent-ink: #ffffff;
      --shadow: 0 8px 24px rgba(31, 41, 55, 0.10);
      --dock-h: 0px;
      --highlight-bg: #eff6ff;
      --highlight-border: #3b82f6;
    }
    @media (prefers-reduced-motion: reduce) {
      * {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
    }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    .sr-only {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 24px;
      padding: 24px;
      max-width: 1400px;
      margin: 0 auto;
    }
    body.has-formulas { grid-template-columns: minmax(0, 1fr); }
    main {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 32px;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
      height: calc(100vh - 48px);
      overflow: hidden;
    }
    aside {
      display: none;
      flex-direction: column;
      gap: 24px;
      height: calc(100vh - 48px);
      overflow-y: auto;
    }
    body.has-formulas aside { display: flex; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 24px;
      box-shadow: var(--shadow);
    }
    .document-header { display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; }
    .document-heading { min-width: 0; }
    .document-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .document-actions a.button { background: transparent; color: #334155; font-weight: 600; }
    .document-actions a.button::after { content: "↗"; margin-left: 7px; color: var(--muted); }
    h1 { margin: 0 0 10px; font-size: 28px; line-height: 1.2; font-weight: 700; }
    h2 { margin: 0 0 16px; font-size: 18px; }
    .metadata {
      font-size: 14px; color: var(--muted); margin-bottom: 24px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center;
    }
    .tag { background: #e8f0ff; color: #0f3f9a; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 500; }
    audio { display: none; }

    button, a.button, summary.button {
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      padding: 8px 16px;
      font: inherit; font-size: 15px; font-weight: 600;
      cursor: pointer; text-decoration: none; white-space: nowrap;
      display: inline-flex; align-items: center; justify-content: center;
    }
    button:hover, a.button:hover, summary.button:hover {
      border-color: #a8b3c4; background: #f9fafb;
    }
    button:focus-visible, a.button:focus-visible, input:focus-visible, summary:focus-visible {
      outline: 3px solid rgba(21, 94, 239, 0.35); outline-offset: 2px;
    }
    #toggle { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); min-width: 80px; }

    #followToggle[aria-pressed="true"],
    .view-switch button[aria-pressed="true"] {
      background: #e8f0ff; border-color: #8bb2ff; color: #0f3f9a;
    }
    #followToggle[data-follow="paused"] {
      background: #fffbeb; border-color: #f59e0b; color: #92400e;
    }
    button:disabled, input:disabled { cursor: wait; opacity: 0.58; }
    button[aria-disabled="true"] { cursor: default; opacity: 0.48; }

    input[type="range"] { width: 100%; accent-color: var(--accent); height: 44px; }
    .transport-wrapper { position: relative; margin-top: 16px; }
    .message {
      position: absolute; left: 12px; bottom: calc(100% + 8px); z-index: 4;
      max-width: min(520px, calc(100vw - 24px)); padding: 8px 12px; border-radius: 8px;
      color: #334155; background: #ffffff; border: 1px solid var(--line);
      box-shadow: var(--shadow); font-size: 13px; font-variant-numeric: tabular-nums;
      transition: opacity 160ms ease;
    }
    .message:empty { visibility: hidden; opacity: 0; pointer-events: none; }
    .transport-position { display: grid; grid-template-columns: auto auto minmax(120px, 1fr) auto; gap: 10px; align-items: center; }
    #followToggle { grid-column: 1; }
    #currentTime { grid-column: 2; }
    #seek { grid-column: 3; }
    #durationTime { grid-column: 4; }
    .transport-position.without-follow { grid-template-columns: auto minmax(120px, 1fr) auto; }
    .transport-position.without-follow #currentTime { grid-column: 1; }
    .transport-position.without-follow #seek { grid-column: 2; }
    .transport-position.without-follow #durationTime { grid-column: 3; }
    .transport-time { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 13px; }
    .transport-actions { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
    .transport-actions > button { min-width: 48px; }
    #toggle { width: 52px; height: 52px; min-width: 52px; padding: 0; font-size: 0; }
    #toggle::before { content: "▶"; font-size: 20px; line-height: 1; transform: translateX(1px); }
    #toggle[data-playing="true"]::before { content: "❚❚"; font-size: 16px; transform: none; letter-spacing: 1px; }
    .speed-stepper {
      display: inline-grid; grid-template-columns: 44px minmax(72px, auto) 44px;
      align-items: stretch; border: 1px solid var(--line); border-radius: 9px; overflow: hidden;
      margin-left: auto; background: #fff;
    }
    .speed-stepper button { min-width: 0; min-height: 44px; padding: 6px 10px; border: 0; border-radius: 0; }
    .speed-stepper button + button { border-left: 1px solid var(--line); }
    #rateReset { font-variant-numeric: tabular-nums; color: #0f3f9a; background: #f5f8ff; }
    #advancedTrigger { width: 44px; padding: 0; font-size: 24px; letter-spacing: 2px; }
    .reader-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
    .view-switch {
      display: inline-flex; padding: 3px; gap: 2px; border: 1px solid var(--line);
      border-radius: 9px; background: #f3f4f6;
    }
    .view-switch button { min-height: 44px; padding: 5px 10px; border-color: transparent; }
    .advanced-layer { position: absolute; inset: auto 0 calc(100% + 8px) auto; z-index: 20; }
    .advanced-scrim { display: none; }
    .advanced-panel {
      width: min(420px, calc(100vw - 32px)); padding: 16px; border: 1px solid var(--line);
      border-radius: 12px; background: var(--panel); box-shadow: var(--shadow);
    }
    .advanced-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
    .advanced-heading h2 { margin: 0; font-size: 16px; }
    #advancedClose { width: 44px; padding: 0; font-size: 22px; }
    .advanced-controls {
      display: grid; gap: 12px; max-height: min(45dvh, 320px); overflow-y: auto;
    }
    .advanced-section {
      padding: 0; border: 0; background: transparent;
    }
    .skips { display: grid; gap: 8px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .skips button { min-width: 0; }
    .skips button { font-variant-numeric: tabular-nums; font-weight: 650; }

    .transcript-container {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      color: #1f2937;
      overflow-y: auto;
      flex: 1;
      position: relative;
    }
    #transcriptText {
      margin: 0; padding: 24px; font-size: 16px; line-height: 1.75;
    }
    #transcriptText h2, #transcriptText h3 {
      margin: 1.5rem 0 0.65rem; color: #172033; line-height: 1.35;
    }
    #transcriptText h2:first-child, #transcriptText h3:first-child { margin-top: 0; }
    #transcriptText h2 { font-size: 21px; }
    #transcriptText h3 { font-size: 18px; }
    #transcriptText p { max-width: 76ch; margin: 0 0 1.15rem; }
    #transcriptText ul, #transcriptText ol { max-width: 76ch; margin: 0 0 1.25rem; padding-left: 1.5rem; }
    #transcriptText li + li { margin-top: 8px; }
    #transcriptText blockquote {
      max-width: 76ch; margin: 0 0 1.25rem; padding: 4px 0 4px 16px;
      border-left: 3px solid #9db8e8; color: #334155;
    }
    #transcriptText strong { font-weight: 750; }
    #transcriptText .inline-code {
      padding: 0.08em 0.3em; border-radius: 4px; background: #eef2f7;
      font: 0.9em/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .sentence-list { padding: 0; margin: 0; }
    .transcript-semantic-list { max-width: 76ch; margin: 1rem 24px 1.25rem; padding-left: 1.5rem; }
    .transcript-semantic-list > li + li { margin-top: 8px; }
    .sentence-list blockquote {
      max-width: 76ch; margin: 1rem 24px 1.25rem; padding: 4px 0 4px 16px;
      border-left: 3px solid #9db8e8; color: #334155;
    }
    .speaker-block { border-bottom: 1px solid var(--line); }
    .speaker-block:last-child { border-bottom: 0; }
    .speaker-name {
      margin: 0; color: #334155; font-size: 14px; font-weight: 700;
      letter-spacing: 0.01em;
    }
    .speaker-paragraph { margin: 0; }
    .sentence-row { cursor: pointer; }
    .article-view .speaker-block { padding: 0 24px; border-bottom: 0; }
    .article-view .speaker-block:first-child { padding-top: 22px; }
    .article-view .speaker-block:last-child { padding-bottom: 22px; }
    .article-view .speaker-block + .speaker-block { margin-top: 1.4rem; }
    .article-view .transcript-semantic-list > .speaker-block + .speaker-block { margin-top: 8px; }
    .article-view .speaker-name { margin-bottom: 8px; }
    .article-view .speaker-paragraph { max-width: 76ch; font-size: 17px; line-height: 1.8; }
    .article-view .transcript-heading {
      max-width: 76ch; margin: 0 0 0.55rem; color: #172033;
      font-size: 21px; line-height: 1.35; font-weight: 750;
    }
    .article-view .transcript-heading.level-3 { font-size: 18px; }
    .article-view .sentence-row {
      display: inline; min-height: 0; padding: 0.08em 0.1em; margin: 0;
      border: 0; border-radius: 4px; background: transparent; color: inherit;
      font: inherit; font-weight: inherit; line-height: inherit; text-align: left;
      white-space: normal; vertical-align: baseline;
    }
    .article-view .sentence-row:hover { background: #e9eff8; }
    .article-view .sentence-row[aria-current="true"] {
      background: var(--highlight-bg); box-shadow: inset 0 -2px var(--highlight-border);
    }
    .article-view .sentence-meta {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
    }
    .sentence-view .speaker-name { padding: 14px 24px 4px; }
    .sentence-view .sentence-row {
      padding: 12px 24px;
      width: 100%; min-height: 0; border: 0;
      border-left: 4px solid transparent;
      border-bottom: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      gap: 6px;
      align-items: flex-start; border-radius: 0; background: transparent;
      color: inherit; font-weight: inherit; text-align: left; white-space: normal;
      font-size: 17px;
      line-height: 1.65;
    }
    .sentence-view .sentence-row:hover { background: #f3f4f6; }
    .sentence-view .sentence-row[aria-current="true"] {
      background: var(--highlight-bg); border-left-color: var(--highlight-border);
    }
    .sentence-meta { font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }
    .sentence-content strong { font-weight: 750; }
    .sentence-content em { font-style: italic; }
    .sentence-content .inline-code {
      padding: 0.08em 0.3em; border-radius: 4px; background: #eef2f7;
      font: 0.9em/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .sync-note {
      padding: 16px; color: #b45309; background: #fffbeb; border-bottom: 1px solid #fde68a;
      font-size: 14px; font-weight: 500; display: none;
    }

    .sentence-row math, #transcriptText math, .formula-card math {
      display: inline math; margin-inline: 0.12em; vertical-align: middle;
    }
    .display-math {
      display: block; width: 100%; margin: 0.9em 0; padding: 0.45em 0;
      overflow-x: auto; text-align: center;
    }
    .display-math math { display: block math; margin-inline: auto; }
    .math-fallback {
      display: inline-block; margin-inline: 0.18em; padding: 0.1em 0.4em;
      border: 1px solid #cbd5e1; border-radius: 4px; background: #f1f5f9;
      color: #0f172a; font: 0.9em/1.4 ui-monospace, monospace; white-space: normal;
    }
    .formula-card {
      padding: 16px; border-bottom: 1px solid var(--line);
    }
    .formula-card:last-child { border-bottom: none; }
    .formula-spoken { font-size: 14px; font-weight: 500; color: #0f3f9a; margin-top: 8px; }

    @media (min-width: 1100px) {
      body.has-formulas { grid-template-columns: minmax(0, 1fr) minmax(340px, 380px); }
    }

    /* Mobile and tablet */
    @media (max-width: 1023px) {
      body {
        grid-template-columns: 1fr;
        padding: 0;
        padding-bottom: var(--dock-h);
      }
      body.has-formulas { grid-template-columns: 1fr; }
      main { border-radius: 0; border: none; height: auto; min-height: 100vh; padding: 20px; box-shadow: none; }
      aside { height: auto; padding: 20px; padding-bottom: 0; overflow-y: visible; }
      .transport-wrapper {
        position: fixed;
        bottom: 0; left: 0; right: 0;
        background: var(--panel);
        border-top: 1px solid var(--line);
        padding: 6px 12px;
        padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px));
        z-index: 100;
        box-shadow: 0 -4px 12px rgba(0,0,0,0.05);
      }
      .transport-position { grid-template-columns: auto auto minmax(64px, 1fr) auto; gap: 6px; }
      .transport-actions { margin-top: 2px; gap: 6px; }
      .transport-actions > button { min-width: 44px; padding-inline: 10px; }
      #toggle { width: 48px; height: 48px; min-width: 48px; }
      .speed-stepper { grid-template-columns: 44px minmax(64px, auto) 44px; }
      .advanced-layer {
        position: fixed; inset: 0; z-index: 200; display: grid; align-items: end;
        padding-bottom: var(--dock-h);
      }
      .advanced-scrim { display: block; position: absolute; inset: 0; background: rgba(16, 24, 40, 0.28); }
      .advanced-panel {
        position: relative; width: 100%; max-height: min(45dvh, 320px); overflow-y: auto;
        border-radius: 12px 12px 0 0; border-inline: 0; border-bottom: 0;
      }
      .transcript-container { min-height: 50vh; margin-bottom: 24px; overflow-y: visible; }
    }
    @media (max-width: 639px) {
      main { padding: 16px; }
      .document-header { flex-direction: column; gap: 4px; }
      .document-actions { justify-content: flex-start; }
      .document-actions a.button { min-height: 44px; padding: 7px 10px; }
      .reader-toolbar { margin-top: 8px; }
      .transport-wrapper { padding-inline: 8px; }
      .transport-position { grid-template-columns: auto auto minmax(44px, 1fr) auto; }
      .transport-time { font-size: 12px; }
      .transport-actions { justify-content: space-between; }
      .speed-stepper { margin-left: 0; }
    }
    @media (max-width: 359px) {
      .transport-actions { flex-wrap: wrap; }
      .speed-stepper { order: 6; flex: 1 1 auto; }
    }
  </style>
</head>
<body>
  <main>
    <header class="document-header">
      <div class="document-heading">
        <h1 id="title"></h1>
        <div class="metadata" id="metadata"></div>
      </div>
      <nav class="document-actions" aria-label="Documentos relacionados">
        <a class="button" id="transcriptLink" href="#" hidden>Transcript</a>
        <a class="button" id="libraryLink" href="#" hidden>Librería</a>
      </nav>
    </header>

    <div class="reader-toolbar">
      <div class="view-switch" id="viewSwitch" role="group" aria-label="Vista del transcript" hidden>
        <button id="articleView" type="button" aria-pressed="true">Artículo</button>
        <button id="sentenceView" type="button" aria-pressed="false">Oraciones</button>
      </div>
    </div>

    <div class="transcript-container" id="transcriptContainer" tabindex="0" aria-label="Transcript">
      <div class="sync-note" id="syncNote">Sin tiempos; seguimiento no disponible</div>
      <div class="sentence-list article-view" id="sentenceList"></div>
      <div id="transcriptText"></div>
    </div>

    <div class="transport-wrapper">
      <div class="message" id="message" aria-live="polite"></div>
      <div class="transport-position">
        <button id="followToggle" type="button" aria-pressed="true" hidden>Seguir</button>
        <span class="transport-time" id="currentTime">0:00</span>
        <input id="seek" type="range" min="0" max="1000" value="0" aria-label="Progreso">
        <span class="transport-time" id="durationTime">0:00</span>
      </div>
      <div class="transport-actions">
        <button type="button" data-skip="-10" aria-label="Rewind 10s">−10</button>
        <button id="toggle" type="button" aria-label="Play">Play</button>
        <button type="button" data-skip="10" aria-label="Forward 10s">+10</button>
        <div class="speed-stepper" role="group" aria-label="Velocidad de reproducción">
          <button id="rateDown" type="button" aria-label="Reducir velocidad">−</button>
          <button id="rateReset" type="button" aria-label="Velocidad normal 1x">1x</button>
          <button id="rateUp" type="button" aria-label="Aumentar velocidad">+</button>
        </div>
        <span class="sr-only" id="rateAnnouncement" aria-live="polite"></span>
        <button id="advancedTrigger" type="button" aria-expanded="false" aria-controls="advancedPanel" aria-label="Controles avanzados">⋯</button>
      </div>
      <div class="advanced-layer" id="advancedLayer" hidden>
        <button class="advanced-scrim" id="advancedScrim" type="button" tabindex="-1" aria-label="Cerrar"></button>
        <section class="advanced-panel" id="advancedPanel" role="dialog" aria-labelledby="advancedTitle">
          <div class="advanced-heading">
            <h2 id="advancedTitle">Controles avanzados</h2>
            <button id="advancedClose" type="button" aria-label="Cerrar">×</button>
          </div>
          <div class="advanced-controls">
          <section class="advanced-section">
            <div class="skips" role="group" aria-label="Saltar en el audio">
              <button type="button" data-skip="-15" aria-label="Retroceder 15 segundos">−15</button>
              <button type="button" data-skip="-10" aria-label="Retroceder 10 segundos">−10</button>
              <button type="button" data-skip="-5" aria-label="Retroceder 5 segundos">−5</button>
              <button type="button" data-skip="5" aria-label="Avanzar 5 segundos">+5</button>
              <button type="button" data-skip="10" aria-label="Avanzar 10 segundos">+10</button>
              <button type="button" data-skip="15" aria-label="Avanzar 15 segundos">+15</button>
            </div>
          </section>
          </div>
        </section>
      </div>
        </div>
  </main>

  <aside>
    <div class="card" id="formulaCard" hidden>
      <h2 id="formulaHeading">Fórmulas</h2>
      <div id="formulaList"></div>
    </div>
  </aside>

  <audio id="audio" preload="auto"></audio>

  <script>
    const data = __PLAYER_DATA__;
    const audio = document.querySelector("#audio");
    const title = document.querySelector("#title");
    const metadata = document.querySelector("#metadata");
    const toggle = document.querySelector("#toggle");
    const seek = document.querySelector("#seek");
    const currentTime = document.querySelector("#currentTime");
    const durationTime = document.querySelector("#durationTime");
    const message = document.querySelector("#message");
    const rateDown = document.querySelector("#rateDown");
    const rateReset = document.querySelector("#rateReset");
    const rateUp = document.querySelector("#rateUp");
    const rateAnnouncement = document.querySelector("#rateAnnouncement");
    const speedStepper = document.querySelector(".speed-stepper");
    const transcriptLink = document.querySelector("#transcriptLink");
    const libraryLink = document.querySelector("#libraryLink");
    const transcriptContainer = document.querySelector("#transcriptContainer");
    const transcriptText = document.querySelector("#transcriptText");
    const sentenceList = document.querySelector("#sentenceList");
    const syncNote = document.querySelector("#syncNote");
    const followToggle = document.querySelector("#followToggle");
    const viewSwitch = document.querySelector("#viewSwitch");
    const articleView = document.querySelector("#articleView");
    const sentenceView = document.querySelector("#sentenceView");
    const formulaCard = document.querySelector("#formulaCard");
    const formulaList = document.querySelector("#formulaList");
    const formulaHeading = document.querySelector("#formulaHeading");
    const advancedTrigger = document.querySelector("#advancedTrigger");
    const advancedLayer = document.querySelector("#advancedLayer");
    const advancedPanel = document.querySelector("#advancedPanel");
    const advancedTitle = document.querySelector("#advancedTitle");
    const advancedClose = document.querySelector("#advancedClose");
    const advancedScrim = document.querySelector("#advancedScrim");
    const skipGroup = document.querySelector(".skips");
    const transportWrapper = document.querySelector(".transport-wrapper");
    const transportPosition = document.querySelector(".transport-position");

    const skipButtons = Array.from(document.querySelectorAll("[data-skip]"));
    const controls = [toggle, seek, ...skipButtons, rateDown, rateReset, rateUp];

    function safeLocalHref(value) {
      if (typeof value !== "string" || !value || value.startsWith("/") || value.startsWith("\\") || value.includes("\\")) return "";
      if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith("//")) return "";
      try {
        let decoded = value;
        for (let i = 0; i < 3; i++) {
          const next = decodeURIComponent(decoded);
          if (next === decoded) break;
          decoded = next;
        }
        if (decoded.startsWith("/") || decoded.startsWith("\\") || decoded.includes("\\") || decoded.split("/").includes("..")) return "";
      } catch (_) {
        return "";
      }
      return value;
    }

    const safeAudio = safeLocalHref(data.audio);

    const ui = data.ui || {};
    title.textContent = data.title || "Audio explainer";
    document.documentElement.lang = data.lang || "es";
    toggle.textContent = ui.play || "Play";
    followToggle.textContent = ui.follow || "Seguir";
    articleView.textContent = ui.article || "Artículo";
    sentenceView.textContent = ui.sentences || "Oraciones";
    advancedTitle.textContent = ui.advanced || "Controles avanzados";
    advancedTrigger.setAttribute("aria-label", ui.advanced || "Controles avanzados");
    advancedClose.setAttribute("aria-label", ui.close || "Cerrar");
    advancedScrim.setAttribute("aria-label", ui.close || "Cerrar");
    skipGroup.setAttribute("aria-label", ui.skip_controls || "Saltar en el audio");
    speedStepper.setAttribute("aria-label", ui.playback_speed || "Velocidad de reproducción");
    rateDown.setAttribute("aria-label", ui.decrease_speed || "Reducir velocidad");
    rateUp.setAttribute("aria-label", ui.increase_speed || "Aumentar velocidad");
    formulaHeading.textContent = ui.formulas || "Fórmulas";
    syncNote.textContent = ui.untimed || "Sin tiempos; seguimiento no disponible";
    seek.setAttribute("aria-label", ui.progress || "Progreso");
    viewSwitch.setAttribute("aria-label", ui.transcript_view || "Vista del transcript");
    transcriptContainer.setAttribute("aria-label", ui.transcript || "Transcript");
    transcriptLink.textContent = ui.transcript_link || ui.transcript || "Transcript";
    libraryLink.textContent = ui.library || "Librería";
    skipButtons.forEach((btn) => {
      const seconds = Number(btn.dataset.skip);
      const action = seconds < 0 ? (ui.rewind || "Retroceder") : (ui.forward || "Avanzar");
      btn.setAttribute("aria-label", `${action} ${Math.abs(seconds)} ${ui.seconds || "segundos"}`);
    });

    if (data.date) {
      const d = document.createElement("span");
      d.textContent = data.date;
      metadata.appendChild(d);
    }
    if (data.tags) {
      data.tags.forEach(tag => {
        const t = document.createElement("span");
        t.className = "tag";
        t.textContent = "#" + tag;
        metadata.appendChild(t);
      });
    }

    const safeLibraryLink = safeLocalHref(data.library_link);
    if (safeLibraryLink) {
      libraryLink.href = safeLibraryLink;
      libraryLink.hidden = false;
    }
    const safeTranscriptLink = safeLocalHref(data.transcript);
    if (safeTranscriptLink) {
      transcriptLink.href = safeTranscriptLink;
      transcriptLink.hidden = false;
    }

    let sourceReady = false;
    let objectUrl = "";
    let isFollowing = true;
    let userScrolled = false;
    let isSeeking = false;
    let messageTimer = null;
    let lastFocusedBeforeDialog = null;

    function setMessage(text, { transient = false } = {}) {
      if (messageTimer) window.clearTimeout(messageTimer);
      messageTimer = null;
      message.textContent = text || "";
      if (transient && text) {
        messageTimer = window.setTimeout(() => { message.textContent = ""; }, 2500);
      }
    }

    const isCompactLayout = () => window.matchMedia("(max-width: 1023px)").matches;

    function updateDockHeight() {
      const height = isCompactLayout() ? Math.ceil(transportWrapper.getBoundingClientRect().height) : 0;
      document.documentElement.style.setProperty("--dock-h", `${height}px`);
    }

    function closeAdvanced() {
      if (advancedLayer.hidden) return;
      advancedLayer.hidden = true;
      advancedTrigger.setAttribute("aria-expanded", "false");
      document.body.style.overflow = "";
      (lastFocusedBeforeDialog || advancedTrigger).focus();
    }

    function openAdvanced() {
      lastFocusedBeforeDialog = document.activeElement;
      advancedLayer.hidden = false;
      advancedTrigger.setAttribute("aria-expanded", "true");
      if (isCompactLayout()) {
        advancedPanel.setAttribute("aria-modal", "true");
        document.body.style.overflow = "hidden";
      } else {
        advancedPanel.removeAttribute("aria-modal");
      }
      requestAnimationFrame(() => advancedClose.focus());
    }

    const MATH_NS = "http://www.w3.org/1998/Math/MathML";
    const ALLOWED_MATH_TAGS = new Set([
      "math", "mrow", "mi", "mn", "mo", "mtext", "mspace", "mfrac",
      "msqrt", "mroot", "msup", "msub", "msubsup", "mover", "munder",
      "munderover", "mtable", "mtr", "mtd", "menclose", "mpadded", "mphantom"
    ]);
    const ALLOWED_MATH_ATTRS = new Set([
      "display", "mathvariant", "stretchy", "fence", "separator", "accent",
      "accentunder", "form", "lspace", "rspace", "minsize", "maxsize", "width",
      "height", "depth", "columnalign", "rowalign", "columnspacing", "rowspacing",
      "linethickness", "bevelled", "notation", "scriptlevel", "displaystyle"
    ]);
    const DROPPED_MATH_TAGS = new Set(["annotation", "annotation-xml", "script", "style"]);

    function sanitizeMathNode(node) {
      if (node.nodeType === 3) return document.createTextNode(node.nodeValue || "");
      if (node.nodeType !== 1) return null;
      const tag = node.localName.toLowerCase();
      if (DROPPED_MATH_TAGS.has(tag)) return null;
      if (!ALLOWED_MATH_TAGS.has(tag)) {
        const fragment = document.createDocumentFragment();
        for (const child of Array.from(node.childNodes)) {
          const safeChild = sanitizeMathNode(child);
          if (safeChild) fragment.appendChild(safeChild);
        }
        return fragment;
      }
      const clean = document.createElementNS(MATH_NS, tag);
      for (const attr of Array.from(node.attributes)) {
        const name = attr.name.toLowerCase();
        if (ALLOWED_MATH_ATTRS.has(name)) clean.setAttribute(name, attr.value);
      }
      for (const child of Array.from(node.childNodes)) {
        const safeChild = sanitizeMathNode(child);
        if (safeChild) clean.appendChild(safeChild);
      }
      return clean;
    }

    function appendInlineMarkdown(parent, text) {
      const tokenPattern = /\*\*(?=\S)(.+?)(?<=\S)\*\*|(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)|`([^`]+)`|\[([^\]]+)\]\([^)]+\)|(?<!\w)\*([^*\n]+)\*(?!\w)|(?<!\w)_([^_\n]+)_(?!\w)/g;
      let cursor = 0;
      let match;
      while ((match = tokenPattern.exec(text)) !== null) {
        if (match.index > cursor) parent.appendChild(document.createTextNode(text.slice(cursor, match.index)));
        let element;
        let value;
        if (match[1] !== undefined || match[2] !== undefined) {
          element = document.createElement("strong");
          value = match[1] ?? match[2];
          appendInlineMarkdown(element, value);
        } else if (match[3] !== undefined) {
          element = document.createElement("code");
          element.className = "inline-code";
          element.textContent = match[3];
        } else if (match[4] !== undefined) {
          element = document.createElement("span");
          value = match[4];
          appendInlineMarkdown(element, value);
        } else {
          element = document.createElement("em");
          value = match[5] ?? match[6];
          appendInlineMarkdown(element, value);
        }
        parent.appendChild(element);
        cursor = tokenPattern.lastIndex;
      }
      if (cursor < text.length) parent.appendChild(document.createTextNode(text.slice(cursor)));
    }

    function appendWithFormulas(parent, text, isSynced) {
      let parts = [{ type: 'text', val: text }];
      if (data.formulas && data.formulas.length > 0) {
        data.formulas.forEach(f => {
          let nextParts = [];
          parts.forEach(p => {
            if (p.type === 'text') {
              let matchVal = isSynced ? f.spoken : f.original;
              if (!matchVal) {
                nextParts.push(p);
                return;
              }
              if (isSynced) {
                let escaped = matchVal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                let pattern = new RegExp(`(^|\\W)(${escaped})(?=\\W|$)`, 'gi');
                let lastIdx = 0;
                let match;
                while ((match = pattern.exec(p.val)) !== null) {
                  let prefix = p.val.substring(lastIdx, match.index + match[1].length);
                  if (prefix) nextParts.push({ type: 'text', val: prefix });
                  nextParts.push({ type: 'hidden-text', val: match[2] });
                  nextParts.push({ type: 'math', val: f.mathml, source: f.original, display: f.display === true });
                  lastIdx = match.index + match[1].length + match[2].length;
                }
                let suffix = p.val.substring(lastIdx);
                if (suffix) nextParts.push({ type: 'text', val: suffix });
              } else {
                let segments = p.val.split(matchVal);
                segments.forEach((seg, i) => {
                  if (seg) nextParts.push({ type: 'text', val: seg });
                  if (i < segments.length - 1) nextParts.push({ type: 'math', val: f.mathml, source: f.original, display: f.display === true });
                });
              }
            } else {
              nextParts.push(p);
            }
          });
          parts = nextParts;
        });
      }
      parts.forEach(p => {
        if (p.type === 'text') {
          appendInlineMarkdown(parent, p.val);
        } else if (p.type === 'hidden-text') {
          let span = document.createElement('span');
          span.style.position = 'absolute'; span.style.width = '1px'; span.style.height = '1px';
          span.style.padding = '0'; span.style.margin = '-1px'; span.style.overflow = 'hidden';
          span.style.clip = 'rect(0, 0, 0, 0)'; span.style.whiteSpace = 'nowrap'; span.style.border = '0';
          span.textContent = p.val;
          parent.appendChild(span);
        } else {
          const parser = new DOMParser();
          const doc = parser.parseFromString(p.val, 'text/html');
          const mathEl = doc.querySelector('math');
          const hasVisibleMath = mathEl && mathEl.querySelector('mrow, mi, mn, mo, mtext, mfrac, msqrt, mroot, msup, msub, msubsup, mover, munder, munderover, mtable');
          if (hasVisibleMath) {
            const safeMath = sanitizeMathNode(mathEl);
            if (safeMath) {
              if (p.display) {
                const wrapper = document.createElement('span');
                wrapper.className = 'display-math';
                wrapper.appendChild(safeMath);
                parent.appendChild(wrapper);
              } else {
                parent.appendChild(safeMath);
              }
            }
          } else {
            const fallback = document.createElement('code');
            fallback.className = 'math-fallback';
            fallback.textContent = p.source || mathEl?.textContent || p.val;
            parent.appendChild(fallback);
          }
        }
      });
    }

    function markdownBlocks(markdown) {
      const blocks = [];
      let paragraph = [];
      let inFence = false;
      const flushParagraph = () => {
        const text = paragraph.join(" ").trim();
        if (text) blocks.push({ type: "paragraph", level: 0, text });
        paragraph = [];
      };
      String(markdown || "").replace(/\r\n?/g, "\n").split("\n").forEach(line => {
        if (/^\s*```/.test(line)) {
          flushParagraph();
          inFence = !inFence;
          return;
        }
        if (inFence) return;
        const heading = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/);
        if (heading) {
          flushParagraph();
          blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
        } else if (!line.trim()) {
          flushParagraph();
        } else {
          const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
          const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
          const quote = line.match(/^\s*>\s?(.*)$/);
          if (unordered || ordered || quote) {
            flushParagraph();
            blocks.push({
              type: quote ? "quote" : "list-item",
              level: 0,
              ordered: Boolean(ordered),
              text: (unordered?.[1] || ordered?.[1] || quote?.[1] || "").trim(),
            });
          } else {
            paragraph.push(line.trim());
          }
        }
      });
      flushParagraph();
      return blocks;
    }

    function markdownPlainText(text) {
      let plain = String(text || "");
      (data.formulas || []).forEach(formula => {
        if (formula.original && formula.spoken) plain = plain.split(formula.original).join(formula.spoken);
      });
      return plain
        .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .replace(/`([^`]+)`/g, "$1")
        .replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)/gm, "")
        .replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*|(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)/g, "$1$2")
        .replace(/(?<!\w)\*([^*\n]+)\*(?!\w)|(?<!\w)_([^_\n]+)_(?!\w)/g, "$1$2");
    }

    function matchingText(text) {
      return markdownPlainText(text)
        .normalize("NFD")
        .toLocaleLowerCase()
        .replace(/[\p{P}\p{Z}\s]/gu, "");
    }

    function alignMarkdownBlocks(segments) {
      const assignments = [];
      let segmentIndex = 0;
      markdownBlocks(data.transcriptText).forEach(block => {
        const blockText = matchingText(block.text);
        let cursor = 0;
        const segmentIndices = [];
        while (segmentIndex < segments.length) {
          const segmentText = matchingText(segments[segmentIndex].text);
          if (!segmentText) { segmentIndex += 1; continue; }
          const foundAt = blockText.indexOf(segmentText, cursor);
          if (foundAt < 0) break;
          segmentIndices.push(segmentIndex);
          cursor = foundAt + segmentText.length;
          segmentIndex += 1;
        }
        if (segmentIndices.length > 0) assignments.push({ ...block, segmentIndices });
      });
      return segmentIndex === segments.length ? assignments : [];
    }

    function markdownSentenceSlices(text) {
      return String(text || "").split(/(?<=[.!?…])\s+/).map(value => value.trim()).filter(Boolean);
    }

    function renderStaticMarkdown(markdown) {
      let activeList = null;
      markdownBlocks(markdown).forEach(block => {
        const plain = markdownPlainText(block.text).trim();
        if (!plain || (block.type === "heading" && plain === String(data.title || "").trim())) return;
        if (/^Generated by audioexplainer\b/i.test(plain)) return;
        if (block.type === "list-item") {
          const listTag = block.ordered ? "OL" : "UL";
          if (!activeList || activeList.tagName !== listTag) {
            activeList = document.createElement(listTag.toLowerCase());
            transcriptText.appendChild(activeList);
          }
          const item = document.createElement("li");
          appendWithFormulas(item, block.text, false);
          activeList.appendChild(item);
          return;
        }
        activeList = null;
        const element = block.type === "heading"
          ? document.createElement(block.level >= 3 ? "h3" : "h2")
          : document.createElement(block.type === "quote" ? "blockquote" : "p");
        appendWithFormulas(element, block.text, false);
        transcriptText.appendChild(element);
      });
    }

    const displayFormulas = (data.formulas || []).filter(f => f.display !== false);
    if (displayFormulas.length > 0) {
      document.body.classList.add("has-formulas");
      formulaCard.hidden = false;
      displayFormulas.forEach(f => {
        const d = document.createElement("div");
        d.className = "formula-card";

        const mathContainer = document.createElement("div");
        appendWithFormulas(mathContainer, f.original, false);
        d.appendChild(mathContainer);

        const spoken = document.createElement("div");
        spoken.className = "formula-spoken";
        spoken.textContent = "🔊 " + f.spoken;
        d.appendChild(spoken);
        formulaList.appendChild(d);
      });
    }

    let validSync = false;
    if (data.sync && Array.isArray(data.sync.segments) && data.sync.segments.length > 0) {
      validSync = true;
      let lastStart = -1;
      for (let seg of data.sync.segments) {
        if (typeof seg.start_s !== 'number' || typeof seg.end_s !== 'number' || typeof seg.text !== 'string' || !Number.isFinite(seg.start_s) || !Number.isFinite(seg.end_s)) {
          validSync = false; break;
        }
        if (seg.start_s > seg.end_s || seg.start_s < lastStart) {
          validSync = false; break;
        }
        lastStart = seg.start_s;
      }
    }
    const hasSync = validSync;
    const EXACT_SYNC_SOURCES = new Set(["edge-sentence-boundary"]);
    const estimatedSync = hasSync && !EXACT_SYNC_SOURCES.has(data.sync.source);
    const rowElements = [];
    let activeRowIndex = -1;
    let followResumeTimer = null;
    let followPausedByUser = false;

    function resumeFollowing() {
      if (followResumeTimer) window.clearTimeout(followResumeTimer);
      followResumeTimer = null;
      isFollowing = true;
      userScrolled = false;
      followPausedByUser = false;
      followToggle.setAttribute("aria-pressed", "true");
      followToggle.dataset.follow = "on";
      followToggle.setAttribute("aria-label", ui.follow || "Seguir");
      setMessage(ui.follow_resumed || "Seguimiento reanudado", { transient: true });
      requestAnimationFrame(() => scrollActiveSentence(true));
    }

    function scrollActiveSentence(force = false) {
      if (!isFollowing || activeRowIndex < 0 || !rowElements[activeRowIndex]) return;
      const activeSentence = rowElements[activeRowIndex].element;
      const sentenceRect = activeSentence.getBoundingClientRect();
      const mobileLayout = isCompactLayout();
      const containerRect = transcriptContainer.getBoundingClientRect();
      const safeTop = mobileLayout ? window.innerHeight * 0.15 : containerRect.top + containerRect.height * 0.2;
      const safeBottom = mobileLayout ? transportWrapper.getBoundingClientRect().top - 12 : containerRect.top + containerRect.height * 0.8;
      if (!force && sentenceRect.top >= safeTop && sentenceRect.bottom <= safeBottom) return;
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
      if (mobileLayout) {
        const targetMiddle = safeTop + Math.max(0, safeBottom - safeTop) / 2;
        const sentenceMiddle = sentenceRect.top + sentenceRect.height / 2;
        window.scrollBy({ top: sentenceMiddle - targetMiddle, behavior });
      } else {
        activeSentence.scrollIntoView({ behavior, block: "center" });
      }
    }

    function temporarilyPauseFollowing() {
      if (!hasSync || followPausedByUser) return;
      if (isFollowing) {
        isFollowing = false;
        followToggle.setAttribute("aria-pressed", "true");
        followToggle.dataset.follow = "paused";
        followToggle.setAttribute("aria-label", `${ui.follow_paused || "Seguimiento pausado"}; ${ui.follow_resumed || "se reanudará automáticamente"}`);
        setMessage(ui.follow_paused || "Seguimiento pausado mientras te desplazas");
      }
      userScrolled = true;
      if (followResumeTimer) window.clearTimeout(followResumeTimer);
      if (audio.paused) {
        followResumeTimer = null;
        return;
      }
      followResumeTimer = window.setTimeout(() => {
        resumeFollowing();
      }, 5000);
    }

    function setTranscriptView(view) {
      const useArticleView = view !== "sentences";
      sentenceList.classList.toggle("article-view", useArticleView);
      sentenceList.classList.toggle("sentence-view", !useArticleView);
      articleView.setAttribute("aria-pressed", String(useArticleView));
      sentenceView.setAttribute("aria-pressed", String(!useArticleView));
      setMessage(useArticleView ? (ui.article_view || "Vista de artículo") : (ui.sentence_view || "Vista por oraciones"), { transient: true });
      if (activeRowIndex !== -1 && isFollowing) {
        requestAnimationFrame(() => scrollActiveSentence(true));
      }
    }

    if (hasSync) {
      if (estimatedSync) {
        syncNote.textContent = ui.estimated || "Seguimiento aproximado para esta voz";
        syncNote.style.display = "block";
      }
      transcriptText.hidden = true;
      followToggle.hidden = false;
      viewSwitch.hidden = false;
      const createSentence = (seg, i, displayText = seg.text) => {
        const speaker = typeof seg.speaker === "string" ? seg.speaker.trim() : "";
        const sentence = document.createElement("button");
        sentence.type = "button";
        sentence.className = "sentence-row";
        sentence.dataset.index = i;
        sentence.setAttribute("aria-label", `${markdownPlainText(displayText)} · ${fmt(seg.start_s)}${speaker ? ` · ${speaker}` : ""}`);

        const contentSpan = document.createElement("span");
        contentSpan.className = "sentence-content";
        appendWithFormulas(contentSpan, displayText, displayText === seg.text);
        sentence.appendChild(contentSpan);

        const metaSpan = document.createElement("span");
        metaSpan.className = "sentence-meta";
        let metaText = fmt(seg.start_s);
        if (speaker) metaText += ` · ${speaker}`;
        metaSpan.textContent = metaText;
        sentence.appendChild(metaSpan);

        sentence.addEventListener("click", () => seekTo(seg.start_s));
        rowElements.push({ element: sentence, start: seg.start_s, end: seg.end_s });
        return sentence;
      };

      const assignments = alignMarkdownBlocks(data.sync.segments);
      if (assignments.length > 0) {
        let activeSemanticList = null;
        assignments.forEach(assignment => {
          let block;
          if (assignment.type === "list-item") {
            const listTag = assignment.ordered ? "OL" : "UL";
            if (!activeSemanticList || activeSemanticList.tagName !== listTag) {
              activeSemanticList = document.createElement(listTag.toLowerCase());
              activeSemanticList.className = "transcript-semantic-list";
              sentenceList.appendChild(activeSemanticList);
            }
            block = document.createElement("li");
            activeSemanticList.appendChild(block);
          } else {
            activeSemanticList = null;
            block = document.createElement(assignment.type === "quote" ? "blockquote" : "section");
            sentenceList.appendChild(block);
          }
          block.className = "speaker-block paragraph-block";
          const firstSegment = data.sync.segments[assignment.segmentIndices[0]];
          const speaker = typeof firstSegment.speaker === "string" ? firstSegment.speaker.trim() : "";
          if (speaker) {
            const speakerName = document.createElement("h2");
            speakerName.className = "speaker-name";
            speakerName.textContent = speaker;
            block.appendChild(speakerName);
          }

          const container = assignment.type === "heading"
            ? document.createElement(assignment.level >= 3 ? "h3" : "h2")
            : document.createElement("p");
          container.className = assignment.type === "heading"
            ? `transcript-heading level-${Math.min(Math.max(assignment.level, 2), 3)}`
            : "speaker-paragraph";
          const slices = markdownSentenceSlices(assignment.text);
          assignment.segmentIndices.forEach((segmentIndex, position) => {
            if (position > 0) container.appendChild(document.createTextNode(" "));
            const segment = data.sync.segments[segmentIndex];
            const displayText = slices.length === assignment.segmentIndices.length ? slices[position] : segment.text;
            container.appendChild(createSentence(segment, segmentIndex, displayText));
          });
          block.appendChild(container);
        });
      } else {
        let currentSpeaker = null;
        let currentPart = null;
        let currentParagraph = null;
        data.sync.segments.forEach((seg, i) => {
          const speaker = typeof seg.speaker === "string" ? seg.speaker.trim() : "";
          if (!currentParagraph || speaker !== currentSpeaker || seg.part_index !== currentPart) {
            const block = document.createElement("section");
            block.className = "speaker-block paragraph-block";
            if (speaker) {
              const speakerName = document.createElement("h2");
              speakerName.className = "speaker-name";
              speakerName.textContent = speaker;
              block.appendChild(speakerName);
            }
            currentParagraph = document.createElement("p");
            currentParagraph.className = "speaker-paragraph";
            block.appendChild(currentParagraph);
            sentenceList.appendChild(block);
            currentSpeaker = speaker;
            currentPart = seg.part_index;
          }
          if (currentParagraph.childNodes.length > 0) currentParagraph.appendChild(document.createTextNode(" "));
          currentParagraph.appendChild(createSentence(seg, i));
        });
      }
      setTranscriptView("article");
    } else {
      transportPosition.classList.add("without-follow");
      syncNote.style.display = "block";
      sentenceList.hidden = true;
      if (data.transcriptText) {
        renderStaticMarkdown(data.transcriptText);
      } else {
        transcriptContainer.hidden = true;
      }
    }

    const setControlsDisabled = (disabled) => {
      controls.forEach((control) => { control.disabled = disabled; });
    };

    function fmt(seconds) {
      if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
      const total = Math.floor(seconds);
      const m = Math.floor(total / 60);
      const s = String(total % 60).padStart(2, "0");
      return `${m}:${s}`;
    }

    const knownDuration = () => Number.isFinite(audio.duration) ? audio.duration : (data.duration || 0);
    const clampTime = (seconds) => Math.max(0, Math.min(knownDuration() || Number.MAX_SAFE_INTEGER, seconds));
    const MIN_RATE_STEPS = 15;
    const MAX_RATE_STEPS = 40;
    const rateSteps = () => Math.max(MIN_RATE_STEPS, Math.min(MAX_RATE_STEPS, Math.round(Number(audio.playbackRate) * 20)));
    const rateLabel = (steps = rateSteps()) => `${String(steps / 20).replace(/\.0+$/, "")}x`;

    function setRateSteps(steps, { announce = true } = {}) {
      const bounded = Math.max(MIN_RATE_STEPS, Math.min(MAX_RATE_STEPS, Math.round(steps)));
      const currentSteps = rateSteps();
      if (bounded === currentSteps) {
        if (announce && bounded === MIN_RATE_STEPS) rateAnnouncement.textContent = ui.minimum_speed || "Velocidad mínima";
        if (announce && bounded === MAX_RATE_STEPS) rateAnnouncement.textContent = ui.maximum_speed || "Velocidad máxima";
        return;
      }
      audio.playbackRate = bounded / 20;
      if (announce) rateAnnouncement.textContent = `${ui.current_speed || "Velocidad actual"} ${rateLabel(bounded)}`;
      render();
    }

    const render = () => {
      const duration = knownDuration();
      const current = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
      if (!isSeeking) seek.value = duration > 0 ? String(Math.round((current / duration) * 1000)) : "0";
      currentTime.textContent = fmt(current);
      durationTime.textContent = fmt(duration);
      const playing = !audio.paused;
      toggle.dataset.playing = String(playing);
      toggle.setAttribute("aria-label", playing ? (ui.pause || "Pausa") : (ui.play || "Play"));
      const steps = rateSteps();
      const speedLabel = rateLabel(steps);
      rateReset.textContent = speedLabel;
      rateDown.setAttribute("aria-disabled", String(steps === MIN_RATE_STEPS));
      rateUp.setAttribute("aria-disabled", String(steps === MAX_RATE_STEPS));
      const isNormalSpeed = steps === 20;
      rateReset.removeAttribute("aria-disabled");
      rateReset.setAttribute("aria-label", isNormalSpeed
        ? `${ui.normal_speed || "Velocidad normal"} 1x`
        : `${ui.current_speed || "Velocidad actual"} ${speedLabel}; ${ui.reset_speed || "restablecer a 1x"}`);

      if (hasSync && !transcriptContainer.hidden) {
        let l = 0, r = rowElements.length - 1;
        let highestStart = -1;
        while (l <= r) {
          let mid = Math.floor((l + r) / 2);
          if (rowElements[mid].start <= current) {
            highestStart = mid; l = mid + 1;
          } else {
            r = mid - 1;
          }
        }
        let found = -1;
        if (highestStart !== -1) {
          for (let i = highestStart; i >= 0; i--) {
            if (current <= rowElements[i].end) { found = i; break; }
          }
        }

        if (found !== activeRowIndex) {
          if (activeRowIndex !== -1) { rowElements[activeRowIndex].element.removeAttribute("aria-current"); }
          activeRowIndex = found;
          if (found !== -1) {
            const activeLi = rowElements[found].element;
            activeLi.setAttribute("aria-current", "true");
            if (isFollowing && !userScrolled) scrollActiveSentence(false);
          }
        }
      }
    };

    const seekTo = (seconds) => {
      const target = clampTime(seconds);
      if (typeof audio.fastSeek === "function") { audio.fastSeek(target); }
      else { audio.currentTime = target; }
      render();
      return target;
    };

    const loadAudioSource = async () => {
      setControlsDisabled(true);
      setMessage(ui.loading || "Cargando audio...");
      if (!safeAudio) {
        sourceReady = false;
        setMessage(ui.audio_error || "No se pudo cargar el audio");
        setControlsDisabled(true);
        return;
      }
      try {
        const response = await fetch(safeAudio, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        audio.src = objectUrl;
        setMessage(ui.ready || "Audio listo", { transient: true });
      } catch (error) {
        audio.src = safeAudio;
        setMessage(ui.ready || "Audio listo", { transient: true });
      } finally {
        sourceReady = true; audio.load(); setControlsDisabled(false); render();
      }
    };

    toggle.addEventListener("click", async () => {
      if (!sourceReady) return;
      try {
        if (audio.paused) {
          await audio.play();
          if (hasSync && !isFollowing && !followPausedByUser) resumeFollowing();
        } else {
          audio.pause();
        }
      } catch (_) {
        setMessage(ui.audio_error || "No se pudo cargar el audio");
      }
      render();
    });

    skipButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!sourceReady) return;
        const delta = Number(btn.dataset.skip);
        seekTo(audio.currentTime + delta);
      });
    });

    rateDown.addEventListener("click", () => { if (sourceReady) setRateSteps(rateSteps() - 1); });
    rateUp.addEventListener("click", () => { if (sourceReady) setRateSteps(rateSteps() + 1); });
    rateReset.addEventListener("click", () => { if (sourceReady && rateSteps() !== 20) setRateSteps(20); });
    rateReset.addEventListener("keydown", (event) => {
      if (!sourceReady) return;
      const actions = {
        ArrowLeft: () => setRateSteps(rateSteps() - 1),
        ArrowDown: () => setRateSteps(rateSteps() - 1),
        ArrowRight: () => setRateSteps(rateSteps() + 1),
        ArrowUp: () => setRateSteps(rateSteps() + 1),
        Home: () => setRateSteps(MIN_RATE_STEPS),
        End: () => setRateSteps(MAX_RATE_STEPS),
        Enter: () => setRateSteps(20),
        " ": () => setRateSteps(20),
      };
      if (actions[event.key]) {
        event.preventDefault();
        actions[event.key]();
      }
    });

    const handleSeekInput = () => {
      if (!sourceReady) return;
      const duration = knownDuration();
      if (duration > 0) {
        seekTo((Number(seek.value) / 1000) * duration);
      }
    };
    seek.addEventListener("pointerdown", () => { isSeeking = true; });
    seek.addEventListener("input", handleSeekInput);
    const finishSeek = () => { isSeeking = false; render(); };
    seek.addEventListener("pointerup", finishSeek);
    seek.addEventListener("pointercancel", finishSeek);
    seek.addEventListener("change", finishSeek);
    seek.addEventListener("change", handleSeekInput);

    followToggle.addEventListener("click", () => {
      if (followResumeTimer) {
        window.clearTimeout(followResumeTimer);
        followResumeTimer = null;
      }
      isFollowing = !isFollowing;
      followPausedByUser = !isFollowing;
      userScrolled = !isFollowing;
      followToggle.setAttribute("aria-pressed", isFollowing.toString());
      if (isFollowing) {
        resumeFollowing();
        render();
      } else {
        followToggle.dataset.follow = "off";
        followToggle.setAttribute("aria-label", ui.follow_disabled || "Seguimiento desactivado");
        setMessage(ui.follow_disabled || "Seguimiento desactivado");
      }
    });

    articleView.addEventListener("click", () => setTranscriptView("article"));
    sentenceView.addEventListener("click", () => setTranscriptView("sentences"));

    advancedTrigger.addEventListener("click", () => advancedLayer.hidden ? openAdvanced() : closeAdvanced());
    advancedClose.addEventListener("click", closeAdvanced);
    advancedScrim.addEventListener("click", closeAdvanced);
    document.addEventListener("pointerdown", (event) => {
      if (advancedLayer.hidden || isCompactLayout()) return;
      const target = event.target instanceof Node ? event.target : null;
      if (target && !advancedPanel.contains(target) && !advancedTrigger.contains(target)) closeAdvanced();
    });
    document.addEventListener("focusin", (event) => {
      if (advancedLayer.hidden || !isCompactLayout()) return;
      if (!advancedPanel.contains(event.target)) advancedClose.focus();
    });
    document.addEventListener("keydown", (event) => {
      if (advancedLayer.hidden) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closeAdvanced();
        return;
      }
      if (event.key !== "Tab" || !isCompactLayout()) return;
      const focusable = Array.from(advancedPanel.querySelectorAll("button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex='-1'])"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    });

    transcriptContainer.addEventListener("wheel", temporarilyPauseFollowing, {passive: true});
    transcriptContainer.addEventListener("touchstart", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest(".sentence-row")) return;
      temporarilyPauseFollowing();
    }, {passive: true});
    transcriptContainer.addEventListener("keydown", (e) => {
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"].includes(e.key)) {
        temporarilyPauseFollowing();
      }
    }, {passive: true});

    ["loadedmetadata", "timeupdate", "play", "pause", "ratechange", "ended"].forEach((eventName) => {
      audio.addEventListener(eventName, render);
    });
    audio.addEventListener("pause", () => {
      if (followResumeTimer) window.clearTimeout(followResumeTimer);
      followResumeTimer = null;
    });
    audio.playbackRate = 1;
    if ("ResizeObserver" in window) {
      new ResizeObserver(updateDockHeight).observe(transportWrapper);
    }
    window.addEventListener("resize", () => {
      updateDockHeight();
      if (!advancedLayer.hidden) closeAdvanced();
    });
    window.addEventListener("beforeunload", () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    });
    render();
    updateDockHeight();
    loadAudioSource();
  </script>
</body>
</html>"""
