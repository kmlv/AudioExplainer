"""audioexplainer — vendor-neutral audio-explainer layer.

The HOST AI (Codex / Claude Code / agy) writes the explainer script; this
package only turns that script into a good neural-voice MP3. No LLM here.

Public surface:
    from audioexplainer.engine import synth_monologue, synth_dialogue, SynthResult
"""

__version__ = "0.1.3"
