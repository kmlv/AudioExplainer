import os
import json
import re
from pathlib import Path
import pytest

from audioexplainer.math_content import prepare_content
from audioexplainer.player import write_player, safe_json_dumps
from audioexplainer.library import _safe_local_href, write_sidecar, rebuild_library


@pytest.mark.parametrize("value", ["javascript:alert(1)", "https://evil.test/x", "../secret", "%2e%2e/secret", "%252e%252e/secret", "/absolute", "\\evil"])
def test_library_rejects_nonlocal_artifact_links(value):
    assert _safe_local_href(value) == ""


def test_library_accepts_relative_artifact_links():
    assert _safe_local_href("demo.player.html") == "demo.player.html"


def test_library_accepts_old_null_sidecar_fields(tmp_path):
    (tmp_path / "legacy.audio.json").write_text(json.dumps({
        "schema_version": 1,
        "title": None,
        "created_at": None,
        "provider": None,
        "duration_s": None,
        "tags": None,
        "formulas": None,
        "sync": None,
    }), encoding="utf-8")
    (tmp_path / "new.audio.json").write_text(json.dumps({
        "schema_version": 1,
        "title": "New",
        "created_at": "2026-07-11T00:00:00Z",
    }), encoding="utf-8")
    rebuild_library(tmp_path)
    content = (tmp_path / "audio-library.html").read_text(encoding="utf-8")
    assert "Untitled" in content
    assert "Unknown" in content


def test_math_content_verbalization():
    text = r"Here is a fraction $\frac{1}{2}$ and $x^2$."
    res = prepare_content(text, "en")

    assert "Here is a fraction" in res["spoken_text"]
    assert "1 over 2" in res["spoken_text"]
    assert "x squared" in res["spoken_text"]

    # Check formulas
    assert len(res["formulas"]) == 2
    assert res["formulas"][0]["spoken"] == "1 over 2"
    assert res["formulas"][1]["spoken"] == "x squared"
    assert "<math" in res["formulas"][0]["mathml"]


def test_math_content_spanish():
    text = r"$\frac{3}{4}$ y $\sqrt{x}$"
    res = prepare_content(text, "es")
    assert "3 sobre 4" in res["spoken_text"]
    assert "raíz cuadrada de x" in res["spoken_text"]


def test_inline_and_display_math_keep_distinct_layout_metadata():
    res = prepare_content(r"Inline $x^2$ y bloque \[y=1\].", "es")

    assert [formula["display"] for formula in res["formulas"]] == [False, True]


def test_math_content_spanish_ces_caption_has_no_raw_latex_commands():
    text = r"""\[
    \text{(2)}\quad
    \rho\equiv\frac{\sigma-1}{\sigma}=1-\frac1\sigma,
    \qquad
    Y=\left[\int_0^1 y(i)^\rho\,di\right]^{1/\rho}.
    \]"""

    res = prepare_content(text, "es")
    spoken = res["formulas"][0]["spoken"]

    assert "(2) rho equivale a sigma menos 1 sobre sigma" in spoken
    assert "1 menos 1 sobre sigma" in spoken
    assert "integral desde 0 hasta 1" in spoken
    for leaked_command in ("quad", "frac", "left", "right", r"\,", r"\equiv"):
        assert leaked_command not in spoken


@pytest.mark.parametrize("formula", [
    r"\mathcal L=\int_0^1p(i)y(i)\,di+\lambda\left\{\bar Y-[\int_0^1y(i)^\rho\,di]^{1/\rho}\right\}",
    r"C(\bar Y,p)=\min_{\{y(i)\ge0\}}\int_0^1p(i)y(i)\,di\quad\text{sujeto a}\quad Y\ge\bar Y",
    r"\frac{\partial Y}{\partial y(i)}=Y^{1/\sigma}y(i)^{-1/\sigma}",
    r"P(p)=\left[\int_0^1p(i)^{1-\sigma}\,di\right]^{\frac1{1-\sigma}}",
    r"\begin{aligned}C&=\bar YP^\sigma\int_0^1p(i)^{1-\sigma}di\\&=\bar YP\end{aligned}",
    r"p(i)=\min\left\{\frac{w}{A_L\gamma_L(i)},\frac{r}{A_K\gamma_K(i)}\right\}",
])
def test_complex_spanish_formula_caption_has_no_latex_leakage(formula):
    spoken = prepare_content(f"$${formula}$$", "es")["formulas"][0]["spoken"]
    forbidden = re.compile(
        r"\\|\b(?:quad|qquad|frac|left|right|mathcal|begin|end|partial|bar|overline)\b|\^"
    )
    assert not forbidden.search(spoken), spoken


def test_spanish_exponents_preserve_following_symbols_and_differentials():
    formulas = [
        r"$$Y^{1-\rho}y(i)^{\rho-1}=Y^{1/\sigma}y(i)^{-1/\sigma}$$",
        r"$$[\{\bar Y(\lambda/p(i))^\sigma\}^{\rho}di]+p(i)^{1-\sigma}di$$",
        r"$$\bar YP^\sigma\int_0^1p(i)^{1-\sigma}di$$",
    ]
    spoken = [prepare_content(value, "es")["formulas"][0]["spoken"] for value in formulas]

    assert "1 menos rho y(i)" in spoken[0]
    assert "1 sobre sigma y(i)" in spoken[0]
    assert "rho di" in spoken[1]
    assert "1 menos sigma di" in spoken[1]
    assert "1 menos sigma di" in spoken[2]


def test_complete_ces_derivation_caption_regression():
    cases = [
        (r"Y=[\int_0^1y(i)^{\frac{\sigma-1}{\sigma}}di]^{\frac{\sigma}{\sigma-1}},\ \sigma>0,\ \sigma\neq1",
         ["sigma menos 1 sobre sigma", "sigma mayor que 0", "sigma distinto de 1"]),
        (r"\rho\equiv\frac{\sigma-1}{\sigma}=1-\frac1\sigma,\quad Y=[\int_0^1y(i)^\rho di]^{1/\rho}",
         ["rho equivale", "1 menos 1 sobre sigma", "potencia de 1 sobre rho"]),
        (r"C(\bar Y,p)=\min_{\{y(i)\ge0\}}\int_0^1p(i)y(i)di\quad\text{sujeto a}\quad Y\ge\bar Y",
         ["Y barra", "mínimo sobre el conjunto donde", "sujeto a", "mayor o igual que"]),
        (r"\mathcal L=\int_0^1p(i)y(i)di+\lambda\{\bar Y-[\int_0^1y(i)^\rho di]^{1/\rho}\}",
         ["L caligráfica", "lambda", "Y barra", "potencia de 1 sobre rho"]),
        (r"\frac{\partial Y}{\partial y(i)}=S^{1/\rho-1}y(i)^{\rho-1}=Y^{1-\rho}y(i)^{\rho-1}=Y^{1/\sigma}y(i)^{-1/\sigma}",
         ["derivada parcial de Y", "1 menos rho y(i)", "1 sobre sigma y(i)", "menos 1 sobre sigma"]),
        (r"p(i)=\lambda\bar Y^{1/\sigma}y(i)^{-1/\sigma}",
         ["lambda", "Y barra", "1 sobre sigma y(i)", "menos 1 sobre sigma"]),
        (r"y(i)=\bar Y(\frac{\lambda}{p(i)})^\sigma=\bar Y(\frac{p(i)}\lambda)^{-\sigma}",
         ["Y barra", "lambda sobre p(i)", "menos sigma"]),
        (r"\bar Y=[\int_0^1\{\bar Y(\frac{\lambda}{p(i)})^\sigma\}^\rho di]^{1/\rho}=\bar Y[\lambda^{\sigma-1}\int_0^1p(i)^{1-\sigma}di]^{1/\rho}",
         ["Y barra", "potencia de rho di", "sigma menos 1", "1 menos sigma di"]),
        (r"\lambda=P(p)\equiv[\int_0^1p(i)^{1-\sigma}di]^{\frac1{1-\sigma}}",
         ["lambda", "P(p)", "1 sobre 1 menos sigma"]),
        (r"y(i)=\bar Y(\frac{p(i)}{P(p)})^{-\sigma}",
         ["Y barra", "p(i) sobre P(p)", "menos sigma"]),
        (r"\begin{aligned}C(\bar Y,p)&=\int_0^1p(i)\bar Y(\frac{p(i)}P)^{-\sigma}di\\&=\bar YP^\sigma\int_0^1p(i)^{1-\sigma}di\\&=\bar YP^\sigma P^{1-\sigma}=\bar YP(p)\end{aligned}",
         ["Y barra", "p(i) sobre P", "menos sigma di", "1 menos sigma di", "Y barra P(p)"]),
        (r"\frac{y(i)}{y(j)}=(\frac{p(i)}{p(j)})^{-\sigma},\quad\frac{\partial\ln[y(i)/y(j)]}{\partial\ln[p(i)/p(j)]}=-\sigma",
         ["y(i) sobre y(j)", "derivada parcial", "logaritmo natural", "menos sigma"]),
        (r"s(i)\equiv\frac{p(i)y(i)}{P\bar Y}=(\frac{p(i)}P)^{1-\sigma}",
         ["p(i)y(i) sobre P Y barra", "p(i) sobre P", "1 menos sigma"]),
        (r"y(i)=A_L\gamma_L(i)\ell(i)+A_K\gamma_K(i)k(i)",
         ["A sub L", "gamma sub L", "ele (i)", "A sub K"]),
        (r"p(i)=\min\{\frac{w}{A_L\gamma_L(i)},\frac{r}{A_K\gamma_K(i)}\}",
         ["mínimo", "w sobre A sub L", "r sobre A sub K"]),
    ]
    forbidden = re.compile(
        r"\\|\b(?:quad|qquad|frac|left|right|mathcal|begin|end|partial|bar|overline)\b|\^"
    )

    assert len(cases) == 15
    for formula, required_fragments in cases:
        spoken = prepare_content(f"$${formula}$$", "es")["formulas"][0]["spoken"]
        assert not forbidden.search(spoken), spoken
        for fragment in required_fragments:
            assert fragment in spoken, (fragment, spoken)


def test_math_advanced_verbalization_en():
    res = prepare_content(r"$\int_0^1 x dx$ and $\sum_{i=1}^n i$ and $\lim_{x \to 0} x_i$ and $\alpha / \beta$", "en")
    text = res["spoken_text"]
    assert "integral from 0 to 1 x dx" in text
    assert "sum from i equals 1 to n i" in text
    assert "limit as x approaches 0 x sub i" in text
    assert "alpha / beta" in text


def test_math_advanced_verbalization_es():
    res = prepare_content(r"$\int_0^1 x dx$ and $\sum_{i=1}^n i$ and $\lim_{x \to 0} x_i$ and $\alpha / \beta$", "es")
    text = res["spoken_text"]
    assert "integral desde 0 hasta 1 x dx" in text
    assert "suma desde i igual a 1 hasta n i" in text
    assert "límite cuando x tiende a 0 x sub i" in text
    assert "alfa sobre beta" in text


def test_safe_json_dumps_malicious_script():
    malicious = "</script><script>alert(1)</script>"
    dumped = safe_json_dumps({"text": malicious})
    assert "</script>" not in dumped
    assert "\\u003c/script\\u003e" in dumped


def test_player_generation(tmp_path):
    audio_path = tmp_path / "test.mp3"
    audio_path.write_bytes(b"")
    transcript = tmp_path / "test.md"
    transcript.write_text("Hello World")

    # No sync HTML
    player_path = write_player(
        audio_path,
        title="Test Title",
        transcript_path=transcript,
        duration_s=10.0,
        sync=None
    )

    content = player_path.read_text("utf-8")
    assert "Test Title" in content
    assert "Sin tiempos; seguimiento no disponible" in content
    assert "test.mp3" in content
    assert "Hello World" in content

    # Sync HTML
    sync_data = {
        "source": "edge-sentence-boundary",
        "segments": [
            {"start_s": 0.0, "end_s": 2.0, "text": "Hello World"}
        ]
    }
    player_path_sync = write_player(
        audio_path,
        title="Sync Title",
        transcript_path=transcript,
        duration_s=2.0,
        sync=sync_data,
        tags=["foo", "bar"],
        date="2026-07-10"
    )

    content_sync = player_path_sync.read_text("utf-8")
    assert "Sync Title" in content_sync
    assert '"foo"' in content_sync
    assert '"bar"' in content_sync
    assert "2026-07-10" in content_sync
    assert "Sin tiempos; seguimiento no disponible" in content_sync
    assert "math-fallback" in content_sync
    assert "sanitizeMathNode(mathEl)" in content_sync
    assert "document.createDocumentFragment()" in content_sync
    assert 'DROPPED_MATH_TAGS = new Set(["annotation", "annotation-xml", "script", "style"])' in content_sync
    assert "ALLOWED_MATH_ATTRS" in content_sync
    assert "mfrac, msqrt" in content_sync
    assert "Controles avanzados" in content_sync
    assert '[hidden] { display: none !important; }' in content_sync
    assert 'class="skips" role="group" aria-label="Saltar en el audio"' in content_sync
    assert 'data-skip="-15" aria-label="Retroceder 15 segundos">−15</button>' in content_sync
    assert 'data-skip="15" aria-label="Avanzar 15 segundos">+15</button>' in content_sync
    assert 'class="speed-stepper" role="group" aria-label="Velocidad de reproducción"' in content_sync
    assert 'id="rateDown"' in content_sync
    assert 'id="rateReset"' in content_sync
    assert 'id="rateUp"' in content_sync
    assert "const MIN_RATE_STEPS = 15;" in content_sync
    assert "const MAX_RATE_STEPS = 40;" in content_sync
    assert "Math.round(Number(audio.playbackRate) * 20)" in content_sync
    assert 'rateDown.setAttribute("aria-disabled"' in content_sync
    assert 'rateUp.setAttribute("aria-disabled"' in content_sync
    assert 'data-speed=' not in content_sync
    assert 'class="seek-icon"' not in content_sync
    assert '<h3 id="skipHeading">' not in content_sync
    assert 'role="dialog" aria-labelledby="advancedTitle"' in content_sync
    assert 'aria-controls="advancedPanel"' in content_sync
    assert 'advancedPanel.setAttribute("aria-modal", "true")' in content_sync
    assert 'advancedPanel.removeAttribute("aria-modal")' in content_sync
    assert 'aria-label="Vista del transcript"' in content_sync
    assert 'id="articleView"' in content_sync
    assert 'id="sentenceView"' in content_sync
    assert 'class="sentence-list article-view"' in content_sync
    assert 'block.className = "speaker-block paragraph-block"' in content_sync
    assert "function appendInlineMarkdown(parent, text)" in content_sync
    assert "function alignMarkdownBlocks(segments)" in content_sync
    assert "function renderStaticMarkdown(markdown)" in content_sync
    assert 'renderStaticMarkdown(data.transcriptText)' in content_sync
    assert 'document.createElement(assignment.level >= 3 ? "h3" : "h2")' in content_sync
    assert 'currentParagraph.appendChild(document.createTextNode(" "))' in content_sync
    assert "function scrollActiveSentence(force = false)" in content_sync
    assert "temporarilyPauseFollowing" in content_sync
    assert "if (!isFollowing) return;" not in content_sync
    assert "if (!hasSync || followPausedByUser) return;" in content_sync
    assert "if (audio.paused)" in content_sync
    assert "function resumeFollowing()" in content_sync
    assert 'audio.addEventListener("pause", () => {' in content_sync
    assert "followPausedByUser" in content_sync
    assert 'setMessage(ui.follow_resumed || "Seguimiento reanudado", { transient: true })' in content_sync
    assert 'target?.closest(".sentence-row")' in content_sync

    estimated_player = write_player(
        audio_path,
        title="Estimated Sync",
        transcript_path=transcript,
        duration_s=2.0,
        sync={
            "source": "duration-weighted-estimate",
            "segments": [{"start_s": 0.0, "end_s": 2.0, "text": "Hello World"}],
        },
    )
    estimated_content = estimated_player.read_text("utf-8")
    assert "Seguimiento aproximado para esta voz" in estimated_content
    assert 'const EXACT_SYNC_SOURCES = new Set(["edge-sentence-boundary"])' in estimated_content
    assert "!EXACT_SYNC_SOURCES.has(data.sync.source)" in estimated_content
    assert 'id="currentTime">0:00</span>' in content_sync
    assert 'id="durationTime">0:00</span>' in content_sync
    assert 'document.createElement(listTag.toLowerCase())' in content_sync
    assert 'document.createElement(block.type === "quote" ? "blockquote" : "p")' in content_sync
    assert '.replace(/^\\s*(?:[-*+]\\s+|\\d+[.)]\\s+|>\\s*)/gm, "")' in content_sync
    assert '(?<!\\w)_([^_\\n]+)_(?!\\w)' in content_sync
    assert '(?<!\\w)__(?=\\S)(.+?)(?<=\\S)__(?!\\w)' in content_sync
    assert 'setTranscriptView("article")' in content_sync
    assert "body.has-formulas { grid-template-columns: minmax(0, 1fr) minmax(340px, 380px); }" in content_sync
    assert "body.has-formulas aside { display: flex; }" in content_sync
    assert "body.has-formulas { grid-template-columns: 1fr; }" in content_sync
    assert 'document.body.classList.add("has-formulas")' in content_sync
    assert 'aria-label="Retroceder 15 segundos"' in content_sync
    assert 'id="transcriptContainer" tabindex="0"' in content_sync
    assert 'id="formulaCard" hidden' in content_sync
    assert "data.formulas.length > 0" in content_sync
    assert "filter(f => f.display !== false)" in content_sync
    assert "display: f.display === true" in content_sync
    assert "wrapper.className = 'display-math'" in content_sync
    assert ".display-math math { display: block math;" in content_sync
    assert "grid-template-columns: minmax(0, 1fr) minmax(340px, 380px)" in content_sync
    assert 'src.className = "formula-source"' not in content_sync


def test_sidecar_and_library_rebuild(tmp_path):
    audio_path = tmp_path / "test.mp3"
    audio_path.touch()

    sidecar_path = write_sidecar(
        audio_path,
        title="Library Test",
        provider="test-provider",
        duration_s=5.5,
        tags=["math", "physics"]
    )

    assert sidecar_path.exists()
    data = json.loads(sidecar_path.read_text("utf-8"))
    assert data["schema_version"] == 1
    assert data["title"] == "Library Test"
    assert data["tags"] == ["math", "physics"]

    # Test library rebuild
    rebuild_library(tmp_path)
    library_path = tmp_path / "audio-library.html"
    assert library_path.exists()

    lib_content = library_path.read_text("utf-8")
    assert "<!-- GENERATOR: AUDIOEXPLAINER -->" in lib_content
    assert "Library Test" in lib_content
    assert "#math" in lib_content
    assert "#physics" in lib_content
    assert "data-search" in lib_content
    assert 'id="filterTag"' in lib_content
    assert 'data-tags="[&quot;math&quot;, &quot;physics&quot;]"' in lib_content
    assert "JSON.parse(el.dataset.tags).includes(tagVal)" in lib_content
    assert 'id="resultsCount" aria-live="polite"' in lib_content
    assert 'for="search"' in lib_content
    assert 'for="filterSync"' in lib_content
    assert '<option value="exact">Exact timing</option>' in lib_content
    assert '<option value="estimated">Approximate timing</option>' in lib_content

    exact = json.loads(sidecar_path.read_text("utf-8"))
    exact["sync"] = {
        "source": "edge-sentence-boundary",
        "segments": [{"text": "Exact", "start_s": 0.0, "end_s": 1.0}],
    }
    sidecar_path.write_text(json.dumps(exact), encoding="utf-8")
    approximate = dict(exact)
    approximate["title"] = "Approximate Library Test"
    approximate["audio"] = "approximate.mp3"
    approximate["sync"] = {
        "source": "duration-weighted-estimate",
        "segments": [{"text": "Approximate", "start_s": 0.0, "end_s": 1.0}],
    }
    (tmp_path / "approximate.audio.json").write_text(
        json.dumps(approximate), encoding="utf-8"
    )
    rebuild_library(tmp_path)
    sync_content = library_path.read_text("utf-8")
    assert 'data-sync="exact"' in sync_content
    assert 'data-sync="estimated"' in sync_content
    assert "Exact timing</span>" in sync_content
    assert "Approximate timing</span>" in sync_content
    assert "syncVal !== 'all' && el.dataset.sync !== syncVal" in sync_content

    # Test idempotent rebuild by verifying content doesn't break
    rebuild_library(tmp_path)
    assert library_path.read_text("utf-8") == sync_content


def test_english_player_preserves_placeholder_text_and_writes_atomically(tmp_path):
    audio_path = tmp_path / "english.mp3"
    audio_path.touch()
    transcript = tmp_path / "english.md"
    transcript.write_text("Keep __TITLE__ exactly.", encoding="utf-8")

    player_path = write_player(
        audio_path,
        title="English demo",
        transcript_path=transcript,
        lang="en",
    )

    content = player_path.read_text(encoding="utf-8")
    assert '<html lang="en">' in content
    assert '"article": "Article"' in content
    assert "Keep __TITLE__ exactly." in content
    assert not list(tmp_path.glob(f".{player_path.name}.*.tmp"))


def test_player_title_preserves_all_template_tokens(tmp_path):
    audio_path = tmp_path / "tokens.mp3"
    audio_path.touch()
    title = "Keep __PLAYER_DATA__, __TITLE__, and __HTML_LANG__"

    player_path = write_player(audio_path, title=title, lang="en")
    content = player_path.read_text(encoding="utf-8")

    assert f"<title>{title}</title>" in content
    assert f'"title": "{title}"' in content


def test_markerless_clobber_safety(tmp_path):
    library_path = tmp_path / "audio-library.html"
    library_path.write_text("Custom user index, do not overwrite")

    rebuild_library(tmp_path)
    assert library_path.read_text() == "Custom user index, do not overwrite"

def test_math_content_regex_escapes():
    text = r"Here is $x$. It costs \$100 and $200. Block: $$ y $$ code: `foo $x$ bar`"
    res = prepare_content(text, "en")

    formulas = res["formulas"]
    # Should only match $x$ and $$ y $$
    assert len(formulas) == 2
    assert formulas[0]["original"] == "$x$"
    assert formulas[1]["original"] == "$$ y $$"

    assert r"\$100 and $200" in res["marked_text"]
    assert "`foo $x$ bar`" in res["marked_text"]

def test_library_search_enrichment(tmp_path):
    audio_path = tmp_path / "test2.mp3"
    audio_path.touch()

    transcript_path = tmp_path / "test2.md"
    transcript_path.write_text("Hidden transcript text about quantum mechanics", encoding="utf-8")

    formulas = [{"spoken": "x squared", "original": "$x^2$"}]

    write_sidecar(
        audio_path,
        title="Enrichment Test",
        provider="test-provider",
        duration_s=5.5,
        transcript_path=transcript_path,
        project="TopSecret",
        content_date="2026-07-10",
        formulas=formulas
    )

    rebuild_library(tmp_path)
    library_path = tmp_path / "audio-library.html"

    lib_content = library_path.read_text("utf-8")

    # Assert data-search contains transcript, formulas, project, content_date
    assert "quantum mechanics" in lib_content
    assert "x squared" in lib_content
    assert "topsecret" in lib_content
    assert "2026-07-10" in lib_content
