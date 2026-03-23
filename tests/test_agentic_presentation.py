from core.ui.agentic_presentation import normalize_focus_text, resolve_agentic_presentation


def test_resolve_agentic_presentation_defaults_to_narrative():
    out = resolve_agentic_presentation("unknown")
    assert out["report_tone"] == "executive"
    assert out["brief_format"] == "narrative"


def test_resolve_agentic_presentation_technical():
    out = resolve_agentic_presentation("Technical report")
    assert out["report_tone"] == "technical"
    assert out["brief_format"] == "technical"


def test_normalize_focus_text_trims_and_handles_none():
    assert normalize_focus_text("  focus on uncertainty  ") == "focus on uncertainty"
    assert normalize_focus_text(None) == ""
