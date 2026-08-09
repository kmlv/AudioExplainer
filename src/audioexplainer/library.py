import json
import os
import sys
from pathlib import Path
from pathlib import PurePosixPath
from datetime import datetime, timezone
import html
from urllib.parse import unquote, urlsplit

SCHEMA_VERSION = 1


def _safe_local_href(value) -> str:
    """Return a safe relative artifact URL, or an empty string."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or value.startswith(("/", "\\")) or "\\" in value:
        return ""
    parsed = urlsplit(value)
    decoded_path = parsed.path
    for _ in range(3):
        next_path = unquote(decoded_path)
        if next_path == decoded_path:
            break
        decoded_path = next_path
    if (
        parsed.scheme
        or parsed.netloc
        or decoded_path.startswith(("/", "\\"))
        or "\\" in decoded_path
        or ".." in PurePosixPath(decoded_path).parts
    ):
        return ""
    return value

def write_sidecar(
    audio_path: Path,
    *,
    title: str,
    provider: str,
    duration_s: float | None,
    transcript_path: Path | None = None,
    player_path: Path | None = None,
    sync: dict | None = None,
    tags: list[str] | None = None,
    project: str | None = None,
    content_date: str | None = None,
    formulas: list[dict] | None = None
) -> Path:
    audio_path = audio_path.resolve()
    sidecar_path = audio_path.with_suffix(".audio.json")

    created_at = datetime.now(timezone.utc).isoformat()

    data = {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "title": title,
        "provider": provider,
        "duration_s": duration_s,
        "audio": audio_path.name,
        "transcript": transcript_path.name if transcript_path else None,
        "player": player_path.name if player_path else None,
        "sync": sync,
        "tags": tags or [],
        "project": project,
        "content_date": content_date,
        "formulas": formulas or []
    }

    # atomic write
    tmp_path = sidecar_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, sidecar_path)
    return sidecar_path

def rebuild_library(directory: Path):
    library_path = directory / "audio-library.html"

    if library_path.exists():
        content = library_path.read_text(encoding="utf-8")
        if "<!-- GENERATOR: AUDIOEXPLAINER -->" not in content:
            print(f"Warning: {library_path} missing generator marker. Skipping library rebuild.", file=sys.stderr)
            return

    sidecars = list(directory.glob("*.audio.json"))
    items = []
    for s in sidecars:
        try:
            with open(s, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("schema_version") == SCHEMA_VERSION:
                    items.append(data)
        except Exception:
            pass

    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)

    html_content = """<!doctype html>
<html lang="en">
<head>
<!-- GENERATOR: AUDIOEXPLAINER -->
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audio Library</title>
<style>
  :root {
    --bg: #f5f7fb;
    --panel: #ffffff;
    --ink: #111827;
    --muted: #5b6472;
    --line: #d8dee8;
    --accent: #155eef;
  }
  body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--ink); margin: 0; padding: 24px; }
  .container { max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 28px; font-weight: 700; margin-top: 0; margin-bottom: 24px; }

  .controls {
    display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; align-items: center;
    background: var(--panel); padding: 16px; border-radius: 12px; border: 1px solid var(--line);
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  }
  input[type="search"] {
    flex: 1; min-width: 250px; padding: 10px 14px; border-radius: 8px; border: 1px solid var(--line); font-size: 15px;
  }
  select {
    padding: 10px 14px; border-radius: 8px; border: 1px solid var(--line); font-size: 15px; background: #fff;
  }
  button.clear-btn {
    padding: 10px 16px; border-radius: 8px; border: 1px solid var(--line); background: #fff; font-size: 15px; cursor: pointer;
  }
  button.clear-btn:hover { background: #f9fafb; }

  .results-count { font-size: 14px; color: var(--muted); width: 100%; font-weight: 500; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px;
  }
  .item {
    background: var(--panel); padding: 20px; border-radius: 12px; border: 1px solid var(--line);
    box-shadow: 0 4px 12px rgba(0,0,0,0.03); display: flex; flex-direction: column;
  }
  .item-title { margin: 0 0 12px; font-size: 18px; line-height: 1.3; }
  .item-title a { color: var(--ink); text-decoration: none; }
  .item-title a:hover { color: var(--accent); text-decoration: underline; }

  .badge { display: inline-block; background: #dcfce7; color: #166534; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 8px; vertical-align: middle; font-weight: 600; text-transform: uppercase;}
  .badge.formula { background: #e0e7ff; color: #3730a3; }

  .tags { margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; }
  .tag { background: #e8f0ff; color: #0f3f9a; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 500; }

  .actions { margin-top: auto; display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .actions a {
    color: var(--ink); text-decoration: none; font-size: 14px; font-weight: 600; padding: 6px 12px; border: 1px solid var(--line); border-radius: 6px;
  }
  .actions a:hover { background: #f9fafb; border-color: #a8b3c4; }
  .actions a.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  .actions a.primary:hover { background: #1d4ed8; }

  .meta { font-size: 13px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 12px; }

  #emptyState { display: none; text-align: center; padding: 40px; color: var(--muted); grid-column: 1 / -1; }

  @media (max-width: 600px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="container">
<h1>Audio Library</h1>

<div class="controls">
  <label class="sr-only" for="search">Search audio library</label>
  <input type="search" id="search" placeholder="Search title, tags, text, formulas...">
  <label class="sr-only" for="filterSync">Synchronization</label>
  <select id="filterSync">
    <option value="all">All</option>
    <option value="exact">Exact timing</option>
    <option value="estimated">Approximate timing</option>
    <option value="untimed">Untimed</option>
  </select>
  <label class="sr-only" for="filterProject">Project</label>
  <select id="filterProject">
    <option value="">All Projects</option>
"""

    projects = sorted({str(it.get("project")) for it in items if it.get("project")})
    for p in projects:
        html_content += f"""    <option value="{html.escape(p)}">{html.escape(p)}</option>
"""

    html_content += """  </select>
  <label class="sr-only" for="filterTag">Tag</label>
  <select id="filterTag">
    <option value="">All Tags</option>
"""
    all_tags = sorted({str(tag) for it in items for tag in (it.get("tags") or [])})
    for tag in all_tags:
        html_content += f"""    <option value="{html.escape(tag.lower())}">#{html.escape(tag)}</option>
"""

    html_content += """  </select>
  <label class="sr-only" for="sortOrder">Sort order</label>
  <select id="sortOrder">
    <option value="newest">Newest first</option>
    <option value="oldest">Oldest first</option>
  </select>
  <button class="clear-btn" id="clearBtn">Clear</button>
  <div class="results-count" id="resultsCount" aria-live="polite"></div>
</div>

<div class="grid" id="list">
"""

    for it in items:
        title = str(it.get("title") or "Untitled")
        created_at = str(it.get("created_at") or "")
        date = created_at.split("T")[0]
        audio = _safe_local_href(it.get("audio", ""))
        player = _safe_local_href(it.get("player", ""))
        raw_tags = it.get("tags")
        tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
        sync = it.get("sync") if isinstance(it.get("sync"), dict) else None
        project = str(it.get("project") or "")
        content_date = str(it.get("content_date") or "")
        raw_formulas = it.get("formulas")
        formulas = [formula for formula in raw_formulas if isinstance(formula, dict)] if isinstance(raw_formulas, list) else []
        provider = str(it.get("provider") or "")
        duration = it.get("duration_s")
        try:
            duration_label = f"{float(duration):.1f}s" if duration is not None else "Unknown"
        except (TypeError, ValueError):
            duration_label = "Unknown"

        sync_kind = "untimed"
        if sync and isinstance(sync.get("segments"), list) and len(sync["segments"]) > 0:
            sync_kind = (
                "exact" if sync.get("source") == "edge-sentence-boundary" else "estimated"
            )

        transcript_text = ""
        tfile = _safe_local_href(it.get("transcript"))
        if tfile:
            tpath = directory / tfile
            if tpath.exists():
                try:
                    transcript_text = tpath.read_text("utf-8")
                except Exception:
                    pass

        formula_str = " ".join(
            f"{str(f.get('spoken') or '')} {str(f.get('original') or '')}" for f in formulas
        )

        search_text = " ".join(filter(None, [
            title,
            " ".join(tags),
            date,
            project,
            content_date,
            transcript_text,
            formula_str
        ])).lower()

        tag_index = json.dumps([str(tag).lower() for tag in tags], ensure_ascii=False)
        html_content += f"""<div class="item" data-search="{html.escape(search_text)}" data-sync="{sync_kind}" data-project="{html.escape(project)}" data-tags="{html.escape(tag_index)}" data-date="{html.escape(created_at)}">
  <h3 class="item-title">"""

        if player:
            html_content += f"""<a href="{html.escape(player)}">{html.escape(title)}</a>"""
        else:
            html_content += html.escape(title)

        if sync_kind == "exact":
            html_content += """<span class="badge">Exact timing</span>"""
        elif sync_kind == "estimated":
            html_content += """<span class="badge">Approximate timing</span>"""
        if len(formulas) > 0:
            html_content += f"""<span class="badge formula">{len(formulas)} Formulas</span>"""

        html_content += f"""</h3>
  <div class="tags">
"""
        for t in tags:
            html_content += f"""<span class="tag">#{html.escape(t)}</span>"""
        html_content += f"""  </div>
  <div class="actions">
"""
        if player: html_content += f"""<a href="{html.escape(player)}" class="primary">▶ Player</a>"""
        if audio: html_content += f"""<a href="{html.escape(audio)}">MP3</a>"""
        if tfile: html_content += f"""<a href="{html.escape(tfile)}">Transcript</a>"""
        html_content += f"""  </div>
  <div class="meta">
    <div><strong>Date:</strong> {html.escape(date)}</div>"""
        if project: html_content += f"""<div><strong>Project:</strong> {html.escape(project)}</div>"""
        html_content += f"""    <div><strong>Provider:</strong> {html.escape(provider)}</div>
    <div><strong>Duration:</strong> {html.escape(duration_label)}</div>
  </div>
</div>
"""

    html_content += """</div>
<div id="emptyState">No matches found.</div>
</div>
<script>
const search = document.getElementById('search');
const filterSync = document.getElementById('filterSync');
const filterProject = document.getElementById('filterProject');
const filterTag = document.getElementById('filterTag');
const sortOrder = document.getElementById('sortOrder');
const clearBtn = document.getElementById('clearBtn');
const list = document.getElementById('list');
const items = Array.from(document.querySelectorAll('.item'));
const resultsCount = document.getElementById('resultsCount');
const emptyState = document.getElementById('emptyState');

function update() {
    const term = search.value.toLowerCase();
    const syncVal = filterSync.value;
    const projVal = filterProject.value;
    const tagVal = filterTag.value;
    const sortVal = sortOrder.value;

    let visibleCount = 0;

    items.forEach(el => {
        let show = true;
        if (term && !el.dataset.search.includes(term)) show = false;
        if (syncVal !== 'all' && el.dataset.sync !== syncVal) show = false;
        if (projVal && el.dataset.project !== projVal) show = false;
        if (tagVal && !JSON.parse(el.dataset.tags).includes(tagVal)) show = false;

        if (show) {
            el.style.display = 'flex';
            visibleCount++;
        } else {
            el.style.display = 'none';
        }
    });

    const visibleItems = items.filter(el => el.style.display !== 'none');
    visibleItems.sort((a, b) => {
        const dA = a.dataset.date;
        const dB = b.dataset.date;
        if (sortVal === 'newest') return dA < dB ? 1 : (dA > dB ? -1 : 0);
        return dA > dB ? 1 : (dA < dB ? -1 : 0);
    });

    visibleItems.forEach(el => list.appendChild(el));

    resultsCount.textContent = `Showing ${visibleCount} of ${items.length} items`;
    emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
}

search.addEventListener('input', update);
filterSync.addEventListener('change', update);
filterProject.addEventListener('change', update);
filterTag.addEventListener('change', update);
sortOrder.addEventListener('change', update);
clearBtn.addEventListener('click', () => {
    search.value = '';
    filterSync.value = 'all';
    filterProject.value = '';
    filterTag.value = '';
    sortOrder.value = 'newest';
    update();
});

update();
</script>
</body>
</html>"""

    tmp_path = library_path.with_suffix(".html.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    os.replace(tmp_path, library_path)
